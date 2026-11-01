"""Context A/B experiment cannot silently retry, widen citations or leak labels."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import evaluate_context_attribution as experiment
from scripts.evaluate_cross_paper_claims import build_cases
from test_cross_paper_experiment import source_fixture


def inputs(tmp_path,monkeypatch):
    corpus,source=source_fixture()
    task=tmp_path/'task.json';task.write_text(json.dumps(source),encoding='utf-8')
    control=tmp_path/'control.json';control.write_text(json.dumps({
        'source_task_sha256':hashlib.sha256(task.read_bytes()).hexdigest(),'cases':build_cases(source)}),encoding='utf-8')
    output=tmp_path/'output'
    monkeypatch.setattr(experiment.sys,'argv',['run','--task',str(task),'--database','unused',
        '--vectors','unused','--control-report',str(control),'--output',str(output)])
    return corpus,control,output


def test_four_attempts_keep_policy_explicit_and_failed_treatment(tmp_path,monkeypatch):
    _,_,output=inputs(tmp_path,monkeypatch);commands=[]
    def execute(command,check):
        commands.append(command)
        arg=lambda key:command[command.index(key)+1]
        claim=json.loads(Path(arg('--claim-file')).read_text(encoding='utf-8'))
        assert 'expected' not in claim and 'required_checks' not in claim
        assert arg('--max-output-tokens')=='4096' and arg('--protocol')=='facet-handles-v5'
        fail=len(commands)==4
        status='supported' if len(commands) in (1,3) else 'insufficient'
        payload={'status':'failed' if fail else 'succeeded','calls':[{'status':'failed' if fail else 'succeeded'}],
            'verification':{'verdicts':[{'status':status}],'assessments':[
                {n:{'status':status} for n in ('attribution','conditions','entailment')}]}}
        child=Path(arg('--output'));child.mkdir()
        (child/'report.json').write_text(json.dumps(payload),encoding='utf-8')
        return SimpleNamespace(returncode=1 if fail else 0)
    monkeypatch.setattr(experiment.subprocess,'run',execute)
    assert experiment.main()==1
    report=json.loads((output/'report.json').read_text(encoding='utf-8'))
    assert len(commands)==len(report['calls'])==report['max_requests']==4
    assert report['runs'][-1]['replay']['status']=='failed'
    assert report['treatment_expectations_met'] is False
    policies=[c[c.index('--verification-context-policy')+1] for c in commands]
    assert policies==['cited-chunk-v1','preceding-children-v1']*2


def test_changed_source_lineage_stops_before_new_output(tmp_path,monkeypatch):
    _,control,output=inputs(tmp_path,monkeypatch)
    data=json.loads(control.read_text(encoding='utf-8'));data['source_task_sha256']='0'*64
    control.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(experiment.subprocess,'run',lambda *args,**kwargs:pytest.fail('Provider attempted'))
    with pytest.raises(ValueError,match='lineage'):experiment.main()
    assert not output.exists()
