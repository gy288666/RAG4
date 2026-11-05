"""Owner-scoped read-only partial views backed by real retained index adapters."""
import pytest

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.user import User
from app.models.research_task import ResearchTaskRecord
from app.research import runtime
from app.research.store import SQLResearchTaskStore
from app.services import index_version_service as versions
from test_research_runtime import published,storage
from test_research_agent import FakeModel,finish


def must_not_run(*args,**kwargs):
    pytest.fail('Read-only partial view touched execution, credentials, or a forbidden dependency')


@pytest.fixture
def failed(published,storage,monkeypatch):
    owner,pending,version,_=published
    task=runtime.create_task(owner,version.id,tuple(s.document_id for s in pending.sources),pending.goal,
        completion=pending.completion,plan_version='research-comparison-v2',vector_store=storage)
    last=task.sources[-1].document_id
    def factory(*args,**kwargs):
        model=FakeModel();generate=model.generate
        def response(operation,payload):
            if operation=='verify' and payload['claims'][0]['document_id']==last:
                raise ValueError('controlled document return failure')
            return generate(operation,payload)
        model.generate=response
        return model
    monkeypatch.setattr(runtime,'JsonResearchModel',factory)
    done=finish(runtime.configured_agent(vector_store=storage),task)
    assert done.status=='failed' and len(done.verification_batches)==2
    monkeypatch.setattr(runtime,'get_vector_store',lambda:storage)
    monkeypatch.setattr(runtime,'JsonResearchModel',must_not_run)
    monkeypatch.setattr(runtime,'RemoteEmbeddingAdapter',must_not_run)
    monkeypatch.setattr(runtime.config_service,'load_runtime_config',must_not_run)
    return owner,done,version


def row_state(task):
    with SessionLocal() as db:
        row=db.get(ResearchTaskRecord,task.id)
        return row.payload_json,row.payload_sha256,row.revision,row.status


def test_owner_reads_cited_partial_without_execution_or_checkpoint_changes(client,user_headers,failed,storage):
    owner,task,_=failed
    before=row_state(task);active=versions.active_state(owner)
    response=client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers,
        params={'expected_revision':task.revision})
    assert response.status_code==200,response.json()
    assert response.headers['cache-control']=='no-store'
    view=response.json()['data']
    assert view['task_id']==task.id and view['task_revision']==task.revision and view['source_task_status']=='failed'
    assert view['task_marked_completed'] is False and view['artifact_attached_to_task'] is False
    assert view['quality_gate_passed'] is False and view['model_calls']==view['embedding_calls']==0
    assert len(view['artifact']['citations'])==2 and len(view['artifact']['citation_sources'])==2
    assert view['unverified_documents']==[task.sources[-1].document_id]
    assert view['markdown'].startswith('# 失败任务的部分比较稿')
    assert row_state(task)==before and SQLResearchTaskStore().load(owner,task.id)==task
    assert versions.active_state(owner)==active
    repeated=client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers).json()['data']
    assert repeated['view_id']==view['view_id']


def test_auth_ownership_revision_and_state_checked_before_vector_initialization(client,user_headers,admin_headers,failed,published,monkeypatch):
    _,task,_=failed
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    url=f'/api/v1/research-tasks/{task.id}/partial-artifact'
    assert client.get(url).status_code==401
    assert client.get(url,headers=admin_headers).status_code==404
    assert client.get('/api/v1/research-tasks/missing/partial-artifact',headers=user_headers).status_code==404
    assert client.get(url,headers=user_headers,params={'expected_revision':task.revision+1}).status_code==409
    assert client.get(url,headers=user_headers,params={'expected_revision':-1}).status_code==400
    pending=published[1]
    assert client.get(f'/api/v1/research-tasks/{pending.id}/partial-artifact',headers=user_headers).status_code==409


@pytest.mark.parametrize('mutation',['changed','deleted'])
def test_changed_or_deleted_source_cannot_be_published(client,user_headers,failed,mutation):
    _,task,_=failed;before=row_state(task)
    with SessionLocal() as db:
        doc=db.get(Document,task.sources[0].document_id)
        if mutation=='changed':
            from pathlib import Path
            Path(doc.local_path).write_text('changed source bytes',encoding='utf-8')
        else:db.delete(doc);db.commit()
    response=client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers)
    assert response.status_code in {400,404}
    assert response.json()['data'] is None and row_state(task)==before


def test_tampered_checkpoint_is_rejected_before_source_initialization(client,user_headers,failed,monkeypatch):
    _,task,_=failed
    with SessionLocal() as db:
        row=db.get(ResearchTaskRecord,task.id);row.payload_json+=' ';db.commit()
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    response=client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers)
    assert response.status_code==400 and response.json()['data'] is None


def test_disabled_owner_cannot_read_partial_view(client,user_headers,failed,monkeypatch):
    owner,task,_=failed
    with SessionLocal() as db:
        db.get(User,owner).status=0;db.commit()
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    assert client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers).status_code==403


@pytest.mark.parametrize('change',['revision','source'])
def test_observed_change_while_rendering_cannot_return_stale_view(client,user_headers,failed,monkeypatch,change):
    owner,task,_=failed
    original=runtime._load_scope;calls=[]
    def scope(*args,**kwargs):
        corpus,bindings,manifest=original(*args,**kwargs)
        calls.append(True)
        if len(calls)==2:
            if change=='revision':
                # Simulate another authorized operation committing a revision.
                SQLResearchTaskStore().save_checkpoint(task,expected_revision=task.revision)
            else:
                bindings=(bindings[0].model_copy(update={'source_sha256':'f'*64}),)+bindings[1:]
        return corpus,bindings,manifest
    monkeypatch.setattr(runtime,'_load_scope',scope)
    response=client.get(f'/api/v1/research-tasks/{task.id}/partial-artifact',headers=user_headers)
    assert response.status_code==(409 if change=='revision' else 400)
    assert response.json()['data'] is None
    current=SQLResearchTaskStore().load(owner,task.id)
    assert current.status=='failed' and current.artifact is None
    assert current.revision==task.revision+(1 if change=='revision' else 0)
