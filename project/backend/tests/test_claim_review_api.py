"""Owner review overlays preserve machine artifacts and never invoke providers."""
from pathlib import Path
import pytest
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.research_task import ResearchTaskRecord
from app.models.user import User
from app.research import runtime
from app.research.store import SQLResearchTaskStore
from app.services import index_version_service as versions
from test_research_runtime import published,storage
from test_research_agent import finish


def must_not_run(*args,**kwargs):raise AssertionError('Review must not execute providers/configuration')


@pytest.fixture
def completed(published,storage,monkeypatch):
    owner,task,version,_=published
    done=finish(runtime.configured_agent(vector_store=storage),task)
    assert done.status=='completed' and len(done.artifact.citations)==3
    monkeypatch.setattr(runtime,'get_vector_store',lambda:storage)
    monkeypatch.setattr(runtime,'JsonResearchModel',must_not_run)
    monkeypatch.setattr(runtime,'RemoteEmbeddingAdapter',must_not_run)
    monkeypatch.setattr(runtime.config_service,'load_runtime_config',must_not_run)
    return owner,done,version


def snapshot(task):
    with SessionLocal() as db:
        row=db.get(ResearchTaskRecord,task.id)
        return row.payload_json,row.payload_sha256,row.revision,row.status


def body(task,decision='withdraw',reason='The cited passage does not support the complete claim.'):
    return {'expected_revision':task.revision,'source_artifact_id':task.artifact.artifact_id,
            'decision':decision,'reason':reason}


def endpoint(task):return f'/api/v1/research-tasks/{task.id}/claims/{task.artifact.citations[0].claim_id}/review'


def test_read_review_is_source_checked_deterministic_and_read_only(client,user_headers,completed):
    owner,task,_=completed;before=snapshot(task)
    response=client.get(f'/api/v1/research-tasks/{task.id}/review',headers=user_headers)
    assert response.status_code==200,response.json()
    assert response.headers['cache-control']=='no-store'
    view=response.json()['data']
    assert view['artifact']==task.artifact.model_dump(mode='json')
    assert all(item['review_status']=='unreviewed' for item in view['items'])
    assert view['quality_gate_passed'] is False and view['events']==[]
    assert view['model_calls']==view['embedding_calls']==0 and snapshot(task)==before
    assert client.get(f'/api/v1/research-tasks/{task.id}/review',headers=user_headers).json()['data']['view_id']==view['view_id']


def test_withdraw_reset_and_retain_append_history_without_rewriting_machine_artifact(client,user_headers,completed):
    owner,task,_=completed;original=task.artifact;active=versions.active_state(owner)
    for index,decision in enumerate(('withdraw','reset','retain')):
        response=client.post(endpoint(task),headers=user_headers,json=body(task,decision))
        assert response.status_code==200,response.json()
        view=response.json()['data'];task=SQLResearchTaskStore().load(owner,task.id)
        assert task.artifact==original and task.status=='completed'
        assert len(task.claim_reviews)==index+1 and task.revision==view['task_revision']
        assert task.claim_reviews[-1].actor_id==owner
        assert view['items'][0]['review_status']=={'withdraw':'withdrawn','reset':'unreviewed','retain':'retained'}[decision]
        assert len(view['artifact']['citations'])==(2 if decision=='withdraw' else 3)
        assert view['source_artifact_id']==original.artifact_id and view['quality_gate_passed'] is False
    assert [e.decision for e in task.claim_reviews]==['withdraw','reset','retain']
    assert versions.active_state(owner)==active


def test_stale_revision_and_wrong_artifact_cannot_append_review(client,user_headers,completed):
    owner,task,_=completed
    assert client.post(endpoint(task),headers=user_headers,json=body(task)).status_code==200
    current=SQLResearchTaskStore().load(owner,task.id);before=snapshot(current)
    assert client.post(endpoint(task),headers=user_headers,json=body(task)).status_code==409
    request=body(current);request['source_artifact_id']='other'
    assert client.post(endpoint(current),headers=user_headers,json=request).status_code==409
    assert snapshot(current)==before


def test_owner_and_state_checks_precede_vector_initialization(client,user_headers,admin_headers,completed,monkeypatch):
    _,task,_=completed
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    url=f'/api/v1/research-tasks/{task.id}/review'
    assert client.get(url).status_code==401
    assert client.get(url,headers=admin_headers).status_code==404
    assert client.post(endpoint(task),headers=admin_headers,json=body(task)).status_code==404
    request=body(task);request['expected_revision']+=1
    assert client.post(endpoint(task),headers=user_headers,json=request).status_code==409


@pytest.mark.parametrize('mutation',['empty','actor','time','unknown_decision'])
def test_invalid_review_input_does_not_write(client,user_headers,completed,mutation):
    _,task,_=completed;before=snapshot(task);request=body(task)
    if mutation=='empty':request['reason']='   '
    if mutation=='actor':request['actor_id']=999
    if mutation=='time':request['reviewed_at']='2000-01-01'
    if mutation=='unknown_decision':request['decision']='gold'
    assert client.post(endpoint(task),headers=user_headers,json=request).status_code==400
    assert snapshot(task)==before


def test_source_drift_blocks_review_without_writing(client,user_headers,completed):
    _,task,_=completed;before=snapshot(task)
    with SessionLocal() as db:path=db.get(Document,task.sources[0].document_id).local_path
    Path(path).write_text('source changed',encoding='utf-8')
    assert client.post(endpoint(task),headers=user_headers,json=body(task)).status_code==400
    assert snapshot(task)==before


def test_disabled_owner_and_unknown_claim_cannot_access_review(client,user_headers,completed,monkeypatch):
    owner,task,_=completed;before=snapshot(task)
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    url=f'/api/v1/research-tasks/{task.id}/claims/foreign/review'
    assert client.post(url,headers=user_headers,json=body(task)).status_code==404
    with SessionLocal() as db:db.get(User,owner).status=0;db.commit()
    assert client.get(f'/api/v1/research-tasks/{task.id}/review',headers=user_headers).status_code==403
    assert client.post(endpoint(task),headers=user_headers,json=body(task)).status_code==403
    assert snapshot(task)==before


def test_pending_task_is_rejected_before_source_adapters(client,user_headers,published,monkeypatch):
    _,task,_,_=published
    monkeypatch.setattr(runtime,'get_vector_store',must_not_run)
    assert client.get(f'/api/v1/research-tasks/{task.id}/review',headers=user_headers).status_code==409


@pytest.mark.parametrize('mutation',['source','revision'])
def test_observed_race_never_commits_a_stale_review(client,user_headers,completed,monkeypatch,mutation):
    owner,task,_=completed;original=runtime._load_scope;calls=[]
    def changed(*args,**kwargs):
        corpus,bindings,manifest=original(*args,**kwargs);calls.append(True)
        if len(calls)==2:
            if mutation=='source':bindings=(bindings[0].model_copy(update={'source_sha256':'f'*64}),*bindings[1:])
            else:SQLResearchTaskStore().save_checkpoint(task,expected_revision=task.revision)
        return corpus,bindings,manifest
    monkeypatch.setattr(runtime,'_load_scope',changed)
    response=client.post(endpoint(task),headers=user_headers,json=body(task))
    assert response.status_code==(400 if mutation=='source' else 409)
    current=SQLResearchTaskStore().load(owner,task.id)
    assert not current.claim_reviews and current.artifact==task.artifact
