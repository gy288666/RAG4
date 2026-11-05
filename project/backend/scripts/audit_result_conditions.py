"""Offline exact-source condition audit of an isolated research checkpoint.

No credentials or model calls. The qualified counterfactual tests this literal
gate only and is never promoted to a semantically verified claim or artifact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('task','database','vectors','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    raw=args.task.read_bytes()
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output.resolve()/'snapshot.sqlite'
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target) as new:
        old.backup(new)
    os.environ['ENV_FILE']=str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI']='false'
    from app.research.tasks import ResearchTask
    from app.research.store import SQLResearchTaskStore
    from app.research.result_conditions import audit_result_conditions
    from app.research.artifacts import EvidenceVerifier,ArtifactComposer,_quote_source
    from app.services.vector_store import LocalVectorStore
    from scripts.reverify_research_claims import frozen_corpus
    task=ResearchTask.model_validate_json(raw)
    if SQLResearchTaskStore().load(task.user_id,task.id)!=task:
        raise ValueError('SQL and JSON snapshots differ')
    digests=lambda:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.vectors.glob('*.json')}
    before=digests()
    corpus=frozen_corpus(task,LocalVectorStore(str(args.vectors)))
    audits=[audit_result_conditions(corpus,c) for c in task.claims if c.facet=='result']
    negative=next(c for c in task.claims if c.document_id=='realm' and c.facet=='result')
    audit=next(a for a in audits if a.claim_id==negative.claim_id)
    if audit.status!='missing' or audit.missing_conditions!=('CC-News',):
        raise ValueError('Frozen REALM missing-condition regression changed')
    positive=negative.model_copy(update={'statement':negative.statement+'（预训练语料X=CC-News）'})
    positive=positive.model_copy(update={'claim_id':positive.expected_id(corpus.corpus_id)})
    positive_audit=audit_result_conditions(corpus,positive)
    if positive_audit.status!='passed':raise ValueError('Qualified condition counterfactual did not pass')
    class NoModel:
        verification_protocol='facet-handles-v5'
        verification_context_policy=task.completion.verification_context_policy
        result_condition_policy='explicit-row-v1'
        def generate(self,*args):raise AssertionError('Condition omission must be blocked without model use')
    verification=EvidenceVerifier(NoModel()).verify(corpus,(negative,))
    artifact=ArtifactComposer().compose(corpus,task.goal,tuple(s.document_id for s in task.sources),
        {s.document_id:s.title for s in task.sources},(negative,),verification)
    if artifact.citations:raise ValueError('Blocked claim was published')
    row_claim=negative.model_copy(update={'citation':audit.row.source})
    row_claim=row_claim.model_copy(update={'claim_id':row_claim.expected_id(corpus.corpus_id)})
    if before!=digests() or raw!=args.task.read_bytes():raise ValueError('Frozen input changed')
    backend=Path(__file__).resolve().parents[1]
    report={'schema':'offline-result-condition-audit-v1','quality_gate_passed':False,
        'annotation_status':'deterministic_literal_audit_not_human_or_semantic_validation',
        'source_task_sha256':hashlib.sha256(raw).hexdigest(),'vector_sha256':before,
        'source_task_id':task.id,'model_calls':0,'embedding_calls':0,'business_database_accessed':False,
        'source_inputs_unchanged':True,'audits':[a.model_dump(mode='json') for a in audits],
        'row_source_locator':_quote_source(corpus,row_claim).model_dump(mode='json'),
        'blocked_claim':negative.model_dump(mode='json'),'blocked_verification':verification.model_dump(mode='json'),
        'blocked_artifact':artifact.model_dump(mode='json'),
        'qualified_counterfactual':{'claim':positive.model_dump(mode='json'),'audit':positive_audit.model_dump(mode='json'),
            'semantic_verification_performed':False,'published_as_supported':False},
        'code_sha256':{str(p.relative_to(backend)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve()]+list((backend/'app/research').glob('*.py'))}}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'blocked':audit.status,'qualified_condition':positive_audit.status,'model_calls':0}))
    return 0


if __name__=='__main__':raise SystemExit(main())
