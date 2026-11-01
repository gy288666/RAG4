"""Recovery never increases quotas, retries semantic failures or overwrites SQL."""
import hashlib
import sqlite3
import httpx
import pytest
from app.research.tasks import TaskBudget
from scripts.resume_research_comparison import require_recoverable,copy_database,credential_base
from test_research_agent import workflow,finish
from test_research_verification_batches import batched


@pytest.fixture
def network_checkpoint(workflow):
    task,_,_,model,agent,_=batched(workflow)
    generate=model.generate
    def fail_last(operation,payload):
        if operation=='verify' and payload['claims'][0]['document_id']=='d2':
            model.calls.append({'operation':operation,'status':'failed','error_type':'ReadTimeout'})
            raise httpx.ReadTimeout('unit network timeout')
        return generate(operation,payload)
    model.generate=fail_last
    return finish(agent,task)


def test_only_last_network_verification_is_admitted_with_retained_batches(network_checkpoint):
    task=network_checkpoint
    assert require_recoverable(task)=='verify-2'
    assert len(task.verification_batches)==2 and task.model_calls_used==6


@pytest.mark.parametrize('mutation',['semantic','pending_paid','completion_budget','step_budget','running','missing_batch'])
def test_invalid_or_over_budget_checkpoint_cannot_start_provider(network_checkpoint,mutation):
    task=network_checkpoint
    if mutation=='semantic':
        steps=tuple(s.model_copy(update={'result':s.result.model_copy(update={'error_type':'ResponseSchemaError'})})
            if s.status=='failed' else s for s in task.steps)
        task=task.model_copy(update={'steps':steps})
    elif mutation=='pending_paid':
        task=task.model_copy(update={'steps':tuple(s.model_copy(update={'status':'pending'}) if s.id=='analyse-0' else s for s in task.steps)})
    elif mutation=='completion_budget':task=task.model_copy(update={'budget':TaskBudget(max_model_calls=6,max_steps=14)})
    elif mutation=='step_budget':task=task.model_copy(update={'budget':TaskBudget(max_steps=11)})
    elif mutation=='running':task=task.model_copy(update={'steps':tuple(s.model_copy(update={'status':'running'}) if s.id=='search-0' else s for s in task.steps)})
    else:task=task.model_copy(update={'verification_batches':task.verification_batches[:1]})
    with pytest.raises(ValueError):require_recoverable(task)


def test_database_copy_retains_parent_and_refuses_existing_destination(tmp_path):
    source=tmp_path/'source.sqlite';destination=tmp_path/'new.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE marker(value TEXT)')
        db.execute("INSERT INTO marker VALUES ('retained')")
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    copy_database(source,destination)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    with sqlite3.connect(destination) as db:assert db.execute('SELECT value FROM marker').fetchone()==('retained',)
    before=destination.read_bytes()
    with pytest.raises(FileExistsError):copy_database(source,destination)
    assert destination.read_bytes()==before


@pytest.mark.parametrize('endpoint',['https://untrusted.test/v1/chat/completions','http://api.siliconflow.cn/v1/chat/completions'])
def test_checkpoint_cannot_redirect_inherited_provider_credentials(endpoint):
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='credential binding'):credential_base(SimpleNamespace(endpoint=endpoint))


def test_expected_provider_binding_is_stable():
    from types import SimpleNamespace
    assert credential_base(SimpleNamespace(endpoint='https://api.siliconflow.cn/v1/chat/completions'))=='https://api.siliconflow.cn/v1'
