"""Four bounded calls: frozen real failures + synthetic transfer diagnostics.

No extraction, activation or business writes. Each policy sees the same claims;
expectations are scored afterwards and never sent to the model. Not a holdout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def outcome(case, report):
    verdict=next(v for v in report.verdicts if v.claim_id==case['claim'].claim_id)
    assessment=next(a for a in report.assessments if a.claim_id==verdict.claim_id)
    matches=lambda actual,expected: actual=='supported' if expected=='supported' else actual!='supported'
    checks={name:getattr(assessment,name).status for name in ('attribution','conditions','entailment')}
    return {'case_id':case['case_id'],'claim_id':verdict.claim_id,'expected':case['expected'],
        'actual':verdict.status,'verdict_matches':matches(verdict.status,case['expected']),
        'checks':checks,'required_checks':case['required_checks'],
        'checks_match':all(matches(checks[k],v) for k,v in case['required_checks'].items())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('task','database','vectors','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    key=os.environ['RAG4_EVAL_API_KEY']
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output.resolve()/'snapshot.sqlite'
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(target) as copy:
        source.backup(copy)
    os.environ['ENV_FILE']=str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI']='false'
    from app.chunking import ChunkingConfig,ChunkingEngine
    from app.chunking.models import ParsedDocument,ParsedBlock,SourceInfo
    from app.research.evidence import EvidenceCorpus
    from app.research.graph import Citation
    from app.research.artifacts import Claim,EvidenceVerifier
    from app.research.tasks import ResearchTask
    from app.research.runtime import _load_scope
    from app.research.model import JsonResearchModel
    from app.services.vector_store import LocalVectorStore
    task=ResearchTask.model_validate_json(args.task.read_text(encoding='utf-8'))
    vectors=LocalVectorStore(str(args.vectors))
    def real_corpus():
        corpus,bindings,_=_load_scope(task.user_id,task.index_version_id,
            tuple(s.document_id for s in task.sources),vectors)
        if corpus.corpus_id!=task.corpus_id or bindings!=task.sources:
            raise ValueError('Source snapshot mismatch')
        return corpus
    corpus=real_corpus()
    realm={c.facet:c for c in task.claims if c.document_id=='realm'}
    corrected=realm['limitation'].model_copy(update={'facet':'method',
        'statement':'通过分别重置检索器或编码器参数，再进行微调，考察预训练对两个组件的贡献。'})
    corrected=corrected.model_copy(update={'claim_id':corrected.expected_id(corpus.corpus_id)})
    def case(name,claim,expected,checks):
        return {'case_id':name,'claim':claim,'expected':expected,'required_checks':checks}
    real=[case('real_method',realm['method'],'supported',{'conditions':'supported'}),
        case('real_missing_condition',realm['result'],'not_supported',{'conditions':'not_supported'}),
        case('real_invented_future_work',realm['limitation'],'not_supported',{'entailment':'not_supported'}),
        case('real_completed_investigation',corrected,'supported',{'conditions':'supported','entailment':'supported'})]
    text=('We encode each passage independently during inference. '
        'We reset the encoder and retriever separately and found both components improve accuracy. '
        'A limitation of our method is failure on handwritten documents.')
    doc=ParsedDocument(document_id='synthetic',file_name='synthetic.txt',parser_version='synthetic-v1',
        source=SourceInfo(uri='synthetic:facet-transfer-v1'),blocks=(ParsedBlock(block_id='b',text=text),))
    chunks=ChunkingEngine().split(doc,ChunkingConfig(child_max_tokens=1800,parent_max_tokens=3600))
    synthetic=EvidenceCorpus(task.user_id,(chunks,))
    chunk=chunks.child_chunks[0]
    citation=Citation(chunk_id=chunk.chunk_id,char_start=0,char_end=len(text),quote=text)
    transfer=[]
    for name,facet,statement,expected,checks in (
        ('transfer_method','method','推理时独立编码每个段落。','supported',{'conditions':'supported'}),
        ('transfer_wrong_stage','method','仅在训练时独立编码段落，推理时不独立编码。','not_supported',{'entailment':'not_supported'}),
        ('transfer_limitation','limitation','该方法在手写文档上失败。','supported',{'conditions':'supported','entailment':'supported'}),
        ('transfer_conjunction','limitation','该方法在手写文档上失败，且尚不清楚编码器和检索器各自的贡献。','not_supported',{'entailment':'not_supported'})):
        claim=Claim(claim_id='pending',document_id='synthetic',facet=facet,statement=statement,citation=citation)
        claim=claim.model_copy(update={'claim_id':claim.expected_id(synthetic.corpus_id)})
        transfer.append(case(name,claim,expected,checks))
    groups=[('real',corpus,real),('synthetic_transfer',synthetic,transfer)]
    fixture=[{'group':name,'corpus_id':group_corpus.corpus_id,'cases':[
        {**c,'claim':c['claim'].model_dump(mode='json')} for c in cases]} for name,group_corpus,cases in groups]
    encoded=json.dumps(fixture,ensure_ascii=False,indent=2)
    (args.output/'cases.json').write_text(encoded,encoding='utf-8')
    report={'schema':'verification-facet-comparison-v1','annotation_status':'development_ai_expectations',
        'quality_gate_passed':False,'max_model_calls':4,'calls':[],'runs':[],
        'source_task_sha256':hashlib.sha256(args.task.read_bytes()).hexdigest(),
        'fixture_sha256':hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
        'business_database_modified':False,'new_extraction':False,
        'limitations':['AI-authored cases are not human validation or an independent holdout',
            'Four real diagnostic claims and four synthetic cases do not measure all paper comparison quality'],
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__)]+list((Path(__file__).resolve().parents[1]/'app/research').glob('*.py'))}}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for name,group_corpus,cases in groups:
        for protocol in ('source-handles-v4','facet-handles-v5'):
            model=JsonResearchModel(task.completion.model_copy(update={
                'verification_protocol':protocol,'max_output_tokens':4096}),api_key=key,max_calls=1)
            row={'group':name,'protocol':protocol,'status':'running'}
            report['runs'].append(row);save()
            try:
                if name=='real':group_corpus=real_corpus()
                verification=EvidenceVerifier(model).verify(group_corpus,tuple(c['claim'] for c in cases))
                if name=='real':real_corpus()
                rows=[outcome(c,verification) for c in cases]
                row.update(status='succeeded',verification=verification.model_dump(mode='json'),rows=rows,
                    verdict_matches=sum(r['verdict_matches'] for r in rows),
                    complete_matches=sum(r['verdict_matches'] and r['checks_match'] for r in rows))
            except Exception as error:
                row.update(status='failed',error_type=type(error).__name__,diagnostics=getattr(error,'diagnostics',()))
            finally:
                report['calls'].extend({**c,'group':name} for c in model.calls)
                save()
            print(json.dumps({k:row[k] for k in ('group','protocol','status','verdict_matches','complete_matches') if k in row}),flush=True)
    return 0 if all(r['status']=='succeeded' for r in report['runs']) else 1


if __name__=='__main__':
    raise SystemExit(main())
