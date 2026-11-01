"""Transfer-case fixtures bind sources; budgets and labels stay outside calls."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.chunking import ChunkingEngine,ChunkingConfig
from app.chunking.models import ParsedDocument,ParsedBlock,SourceInfo
from app.research.artifacts import Claim
from app.research.evidence import EvidenceCorpus
from app.research.graph import Citation
from scripts import evaluate_cross_paper_claims as experiment
from scripts.reverify_research_claims import load_claim_file


def source_fixture():
    sets=[]
    for doc in ('dpr','fid'):
        parsed=ParsedDocument(document_id=doc,file_name=doc+'.txt',parser_version='fixture-v1',
            source=SourceInfo(uri='document:'+doc),blocks=(ParsedBlock(block_id='b',text='Frozen source text.'),))
        sets.append(ChunkingEngine().split(parsed,ChunkingConfig(child_max_tokens=100,parent_max_tokens=200)))
    corpus=EvidenceCorpus(1,tuple(sets));claims=[]
    for doc,facet in (('dpr','dataset'),('dpr','limitation'),('fid','method'),('fid','limitation')):
        chunk=corpus.chunk_sets[doc].child_chunks[0]
        claim=Claim(claim_id='pending',document_id=doc,facet=facet,statement='Original statement',
            citation=Citation(chunk_id=chunk.chunk_id,char_start=0,char_end=len(chunk.text),quote=chunk.text))
        claims.append(claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)}))
    return corpus,{'corpus_id':corpus.corpus_id,'claims':[c.model_dump(mode='json') for c in claims]}


def test_counterfactuals_change_identity_without_manufacturing_source_quotes(tmp_path):
    corpus,source=source_fixture();cases=experiment.build_cases(source)
    assert len({c['claim']['claim_id'] for c in cases})==6
    originals={c['claim_id']:c for c in source['claims']}
    for index,case in enumerate(cases):
        assert case['claim']['citation']==originals[case['source_claim_id']]['citation']
        path=tmp_path/(str(index)+'.json');path.write_bytes(json.dumps(case['claim']).encode())
        assert load_claim_file(path,corpus,('dpr','fid')).claim_id==case['claim']['claim_id']


@pytest.mark.parametrize('context_policy',['cited-chunk-v1','preceding-children-v1'])
@pytest.mark.parametrize('control_kind',['tests','report'])
def test_six_requests_retain_failure_and_never_send_expectations(tmp_path,monkeypatch,context_policy,control_kind):
    corpus,source=source_fixture()
    task=tmp_path/'task.json';task.write_text(json.dumps(source),encoding='utf-8')
    control=tmp_path/'control.json'
    backend=Path(__file__).resolve().parents[1]
    control_data={'unchanged_production_sha256':{}} if control_kind=='tests' else {
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (backend/'app/research').glob('*.py')},
        'source_task_sha256':hashlib.sha256(task.read_bytes()).hexdigest(),
        'replay_script_sha256':hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest()}
    control.write_text(json.dumps(control_data),encoding='utf-8')
    output=tmp_path/'run';commands=[];fixture_hash=None
    monkeypatch.setattr(experiment.sys,'argv',['run','--task',str(task),'--database','unused',
        '--vectors','unused','--control-'+control_kind,str(control),'--output',str(output),
        '--verification-context-policy',context_policy])
    def execute(command,check):
        nonlocal fixture_hash
        commands.append(command)
        arg=lambda name:command[command.index(name)+1]
        assert check is False and '--claim-id' not in command and '--expected' not in command
        claim=load_claim_file(Path(arg('--claim-file')),corpus,('dpr','fid'))
        assert arg('--protocol')=='facet-handles-v5' and arg('--max-output-tokens')=='4096'
        assert arg('--verification-context-policy')==context_policy
        raw=(output/'cases.json').read_bytes()
        current=hashlib.sha256(raw).hexdigest()
        if fixture_hash is None:fixture_hash=current
        assert fixture_hash==current
        fail=len(commands)==2
        payload={'status':'failed' if fail else 'succeeded','calls':[{'status':'failed' if fail else 'succeeded'}],
            'verification':{'verdicts':[{'claim_id':claim.claim_id,'status':'insufficient'}],
                'assessments':[{name:{'status':'insufficient'} for name in ('attribution','conditions','entailment')}]}}
        child=Path(arg('--output'));child.mkdir()
        (child/'report.json').write_text(json.dumps(payload),encoding='utf-8')
        return SimpleNamespace(returncode=1 if fail else 0)
    monkeypatch.setattr(experiment.subprocess,'run',execute)
    assert experiment.main()==1
    report=json.loads((output/'report.json').read_text(encoding='utf-8'))
    assert len(commands)==len(report['calls'])==report['max_requests']==6
    assert report['runs'][1]['replay']['status']=='failed'
    assert report['fixture_sha256']==fixture_hash
    assert report['verification_context_policy']==context_policy


def test_changed_verification_code_stops_before_any_call(tmp_path,monkeypatch):
    _,source=source_fixture()
    task=tmp_path/'task.json';task.write_text(json.dumps(source),encoding='utf-8')
    control=tmp_path/'control.json';control.write_text(json.dumps({'unchanged_production_sha256':{
        'app/research/model.py':'0'*64}}),encoding='utf-8')
    output=tmp_path/'new'
    monkeypatch.setattr(experiment.sys,'argv',['run','--task',str(task),'--database','unused',
        '--vectors','unused','--control-tests',str(control),'--output',str(output)])
    monkeypatch.setattr(experiment.subprocess,'run',lambda *args,**kwargs:pytest.fail('Provider attempted'))
    with pytest.raises(ValueError,match='implementation'):experiment.main()
    assert not output.exists()


@pytest.mark.parametrize('runs,status,code',[
    ([], 'execution_failed',1),
    ([{'replay':{'status':'failed'}}], 'execution_failed',1),
    ([{'replay':{'status':'succeeded'},'verdict_matches':False,'checks_match':False}], 'expectation_mismatch',2),
    ([{'replay':{'status':'succeeded'},'verdict_matches':True,'checks_match':False}], 'expectation_mismatch',2),
    ([{'replay':{'status':'succeeded'},'verdict_matches':True,'checks_match':True}], 'development_expectations_met',0),
])
def test_request_success_cannot_masquerade_as_semantic_success(runs,status,code):
    assert experiment.diagnostic_status(runs)==(status,code)


def test_offline_scoring_preserves_record_and_never_calls_provider(tmp_path,monkeypatch):
    report=tmp_path/'report.json'
    raw=json.dumps({'runs':[{'replay':{'status':'succeeded'},'verdict_matches':False,'checks_match':False}]}).encode()
    report.write_bytes(raw)
    monkeypatch.setattr(experiment.sys,'argv',['score','--score-report',str(report)])
    monkeypatch.setattr(experiment.subprocess,'run',lambda *args,**kwargs:pytest.fail('Provider attempted'))
    assert experiment.main()==2 and report.read_bytes()==raw


@pytest.mark.parametrize('mutation',['source','replay','inventory'])
def test_new_context_control_rejects_drift_before_provider_call(tmp_path,monkeypatch,mutation):
    _,source=source_fixture();backend=Path(__file__).resolve().parents[1]
    task=tmp_path/'task.json';task.write_text(json.dumps(source),encoding='utf-8')
    data={'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (backend/'app/research').glob('*.py')},
        'source_task_sha256':hashlib.sha256(task.read_bytes()).hexdigest(),
        'replay_script_sha256':hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest()}
    if mutation=='source':data['source_task_sha256']='0'*64
    elif mutation=='replay':data['replay_script_sha256']='0'*64
    else:data['code_sha256'].pop('model.py')
    control=tmp_path/'control.json';control.write_text(json.dumps(data),encoding='utf-8')
    output=tmp_path/'new'
    monkeypatch.setattr(experiment.sys,'argv',['run','--task',str(task),'--database','unused','--vectors','unused',
        '--control-report',str(control),'--output',str(output),'--verification-context-policy','preceding-children-v1'])
    monkeypatch.setattr(experiment.subprocess,'run',lambda *args,**kwargs:pytest.fail('Provider attempted'))
    with pytest.raises(ValueError):experiment.main()
    assert not output.exists()
