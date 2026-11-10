"""A preview is an owned, source-validated draft, never a stored or executed task."""
from pathlib import Path
import pytest
from app.core.database import SessionLocal
from app.models.document import Document
from app.research import runtime
from app.research.store import SQLResearchTaskStore
from app.services import index_version_service as versions
from test_research_runtime import published, storage


@pytest.fixture
def draft(published, monkeypatch):
    owner, task, version, config = published
    def forbidden(*args, **kwargs):
        pytest.fail('Preview/create must not initialize a model or execute tools')
    monkeypatch.setattr(runtime, 'JsonResearchModel', forbidden)
    monkeypatch.setattr(runtime, 'RemoteEmbeddingAdapter', forbidden)
    return owner, task, version, config, dict(index_version_id=version.id,
        document_ids=[s.document_id for s in task.sources], goal='Compare methods', plan_version='research-comparison-v2')


def test_preview_and_confirm_are_same_plan_without_execution(client, user_headers, draft):
    owner, _, _, _, body = draft
    before = SQLResearchTaskStore().listing(owner)
    first = client.post('/api/v1/research-tasks/preview', headers=user_headers, json=body)
    assert first.status_code == 200
    assert first.headers['Cache-Control'] == 'no-store'
    preview = first.json()['data']
    assert client.post('/api/v1/research-tasks/preview', headers=user_headers, json=body).json()['data'] == preview
    assert preview['task_created'] is False and preview['model_calls'] == 0
    assert SQLResearchTaskStore().listing(owner) == before
    created = client.post('/api/v1/research-tasks', headers=user_headers, json={**body, 'expected_preview_id': preview['preview_id']})
    assert created.status_code == 200
    task = created.json()['data']
    assert task['status'] == 'pending' and task['revision'] == task['model_calls_used'] == task['tool_calls_used'] == 0
    assert task['steps'] == preview['steps'] and task['budget'] == preview['budget']
    assert versions.active_state(owner) == (None, 0)


@pytest.mark.parametrize('change', ['goal', 'budget', 'model'])
def test_changed_preview_rejects_create_without_writing(client, user_headers, draft, change):
    owner, _, _, config, body = draft
    seal = client.post('/api/v1/research-tasks/preview', headers=user_headers, json=body).json()['data']['preview_id']
    before = SQLResearchTaskStore().listing(owner)
    if change == 'goal': body['goal'] = 'Different goal'
    if change == 'budget': body['budget'] = {'max_steps': 20, 'max_model_calls': 12, 'max_context_chars': 9000}
    if change == 'model': config.llm_model = 'different'
    assert client.post('/api/v1/research-tasks', headers=user_headers, json={**body, 'expected_preview_id': seal}).status_code == 409
    assert SQLResearchTaskStore().listing(owner) == before


def test_changed_source_is_rejected_before_creation(client, user_headers, draft):
    owner, task, _, _, body = draft
    seal = client.post('/api/v1/research-tasks/preview', headers=user_headers, json=body).json()['data']['preview_id']
    with SessionLocal() as db:
        path = db.get(Document, task.sources[0].document_id).local_path
    Path(path).write_text('Changed bytes', encoding='utf-8')
    before = SQLResearchTaskStore().listing(owner)
    assert client.post('/api/v1/research-tasks', headers=user_headers, json={**body, 'expected_preview_id': seal}).status_code == 400
    assert SQLResearchTaskStore().listing(owner) == before


@pytest.mark.parametrize('mutation', ['duplicate', 'too_few', 'foreign', 'budget'])
def test_invalid_scope_or_budget_has_no_write(client, user_headers, draft, mutation):
    owner, _, _, _, body = draft
    if mutation == 'duplicate': body['document_ids'][1] = body['document_ids'][0]
    if mutation == 'too_few': body['document_ids'] = body['document_ids'][:2]
    if mutation == 'foreign': body['index_version_id'] = 'not-owned'
    if mutation == 'budget': body['budget'] = {'max_steps': 1}
    before = SQLResearchTaskStore().listing(owner)
    assert client.post('/api/v1/research-tasks/preview', headers=user_headers, json=body).status_code in (400, 404)
    assert SQLResearchTaskStore().listing(owner) == before


def test_anonymous_preview_is_rejected(client, draft):
    assert client.post('/api/v1/research-tasks/preview', json=draft[-1]).status_code == 401


def test_other_owner_including_admin_cannot_preview_sources(client, admin_headers, draft):
    assert client.post('/api/v1/research-tasks/preview', headers=admin_headers, json=draft[-1]).status_code == 404
