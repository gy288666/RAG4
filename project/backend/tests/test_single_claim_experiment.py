"""Exercise the paid-call cap, frozen lineage and retained failed attempts."""
import hashlib
import json
from pathlib import Path
import pytest
from scripts import evaluate_single_claims as experiment


def inputs(tmp_path,monkeypatch):
    claims=[{'claim_id':'method','facet':'method'},{'claim_id':'limitation','facet':'limitation'}]
    task=tmp_path/'task.json';task.write_text(json.dumps({'claims':claims}),encoding='utf-8')
    model=Path(__file__).resolve().parents[1]/'app/research/model.py'
    batch={'source_task_sha256':hashlib.sha256(task.read_bytes()).hexdigest(),
        'code_sha256':{'model.py':hashlib.sha256(model.read_bytes()).hexdigest()},
        'fixture':[{'group':'real','cases':[
            {'case_id':name,'claim':claim,'expected':expected,'required_checks':{'entailment':expected}}
            for name,claim,expected in zip(('real_method','real_invented_future_work'),claims,('supported','not_supported'))]}]}
    control=tmp_path/'control.json';control.write_text(json.dumps(batch),encoding='utf-8')
    output=tmp_path/'new'
    monkeypatch.setattr(experiment.sys,'argv',['evaluate','--task',str(task),'--database','unused.sqlite',
        '--vectors','unused','--batched-report',str(control),'--output',str(output)])
    return control,batch,output


def test_exactly_four_scoped_attempts_keep_a_failure_without_retry(tmp_path,monkeypatch):
    from types import SimpleNamespace
    _,_,output=inputs(tmp_path,monkeypatch)
    commands=[]
    def execute(command,check):
        commands.append(command)
        assert check is False
        arg=lambda name:command[command.index(name)+1]
        assert arg('--max-output-tokens')=='4096' and command.count('--claim-id')==1
        assert '--resume' not in command and '--expected' not in command
        fail=len(commands)==2
        status='supported' if arg('--claim-id')=='method' else 'insufficient'
        result={'status':'failed' if fail else 'succeeded',
            'calls':[{'status':'failed' if fail else 'succeeded','error_type':'ReadTimeout' if fail else None}],
            'verification':{'verdicts':[{'status':status}],'assessments':[
                {k:{'status':status} for k in ('attribution','conditions','entailment')}]}}
        folder=Path(arg('--output'));folder.mkdir()
        (folder/'report.json').write_text(json.dumps(result),encoding='utf-8')
        return SimpleNamespace(returncode=1 if fail else 0)
    monkeypatch.setattr(experiment.subprocess,'run',execute)
    assert experiment.main()==1
    report=json.loads((output/'report.json').read_text(encoding='utf-8'))
    assert len(commands)==len(report['calls'])==report['max_requests']==4
    assert report['runs'][1]['replay']['calls'][0]['error_type']=='ReadTimeout'
    assert len({c[c.index('--output')+1] for c in commands})==4


@pytest.mark.parametrize('mutation',['task','code'])
def test_changed_control_is_rejected_before_any_request(tmp_path,monkeypatch,mutation):
    control,batch,output=inputs(tmp_path,monkeypatch)
    if mutation=='task':batch['source_task_sha256']='0'*64
    else:batch['code_sha256']['model.py']='0'*64
    control.write_text(json.dumps(batch),encoding='utf-8')
    monkeypatch.setattr(experiment.subprocess,'run',lambda *args,**kwargs:pytest.fail('Provider attempted'))
    with pytest.raises(ValueError):experiment.main()
    assert not output.exists()
