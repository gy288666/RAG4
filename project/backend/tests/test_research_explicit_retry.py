"""Finished network retry preserves quotas, evidence and every failed attempt."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from app.core.database import SessionLocal
from app.models.document import Document
from app.research import runtime
from app.research.agent import ResearchAgent, TaskConflict
from app.research.recovery import retry_decision, retry_candidate
from app.research.store import SQLResearchTaskStore
from app.research.tasks import TaskBudget, ResearchTask, comparison_plan
from test_research_agent import workflow, finish
from test_research_runtime import published, storage


def timeout_context(task):
    raise httpx.ConnectTimeout('offline fixture, no real network')


@pytest.fixture
def stopped(published, monkeypatch):
    owner, task, version, _ = published
    store = SQLResearchTaskStore()
    failed = ResearchAgent(store, timeout_context).step(owner, task.id)
    def forbidden(*a, **kw): pytest.fail('Retry touched model/credentials')
    monkeypatch.setattr(runtime, 'RemoteEmbeddingAdapter', forbidden)
    monkeypatch.setattr(runtime, 'JsonResearchModel', forbidden)
    monkeypatch.setattr(runtime.config_service, 'load_runtime_config', forbidden)
    return owner, failed, store


def test_api_retry_only_prepares_pending_retains_budget_and_attempt(client, user_headers, stopped):
    owner, failed, store = stopped
    url = f'/api/v1/research-tasks/{failed.id}/retry'
    before = store.load(owner, failed.id)
    response = client.get(url, headers=user_headers)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    decision = response.json()['data']
    assert decision['eligible'] and decision['sources_validated']
    assert store.load(owner, failed.id) == before
    response = client.post(url, headers=user_headers, json={'expected_revision': failed.revision})
    assert response.status_code == 200
    restored = store.load(owner, failed.id)
    assert restored.status == 'pending' and restored.revision == failed.revision + 1
    assert restored.budget == failed.budget and restored.tool_calls_used == failed.tool_calls_used
    assert restored.model_calls_used == failed.model_calls_used
    assert restored.bundles == failed.bundles and restored.claims == failed.claims
    assert restored.verification_batches == failed.verification_batches
    assert restored.retry_events[0].failed_step == failed.steps[0]
    assert restored.steps[0].result is None and restored.steps[0].finished_at is None
    assert client.post(url, headers=user_headers, json={'expected_revision': failed.revision}).status_code == 409
    assert store.load(owner, failed.id) == restored


def test_two_retries_keep_history_and_can_finish_without_quota_reset(workflow):
    task, _, store, _, _, context = workflow
    agent = ResearchAgent(store, timeout_context)
    first = agent.step(task.user_id, task.id)
    ready = store.save_checkpoint(retry_candidate(first), expected_revision=first.revision)
    second = agent.step(task.user_id, task.id)
    assert retry_decision(second).eligible
    ready = store.save_checkpoint(retry_candidate(second), expected_revision=second.revision)
    done = finish(ResearchAgent(store, context), ready)
    assert done.status == 'completed' and len(done.retry_events) == 2
    assert done.retry_events[0].failed_step == first.steps[0]
    assert done.retry_events[1].failed_step == second.steps[0]
    assert done.tool_calls_used == len(done.steps) + 2
    assert done.budget == task.budget
    assert ResearchTask.model_validate_json(done.model_dump_json()) == done


def test_legacy_control_history_is_not_a_proof_that_old_call_stopped(workflow):
    task, _, store, _, _, _ = workflow
    agent = ResearchAgent(store, timeout_context)
    failed = agent.step(task.user_id, task.id)
    paused = agent.control(task.user_id, task.id, 'pause', failed.revision)
    pending = agent.control(task.user_id, task.id, 'resume', paused.revision)
    failed = agent.step(task.user_id, task.id)
    assert retry_decision(failed).reason == 'unaccounted_history'
    with pytest.raises(TaskConflict): retry_candidate(failed)


@pytest.mark.parametrize('mutation,reason', [('running', 'attempt_not_finished'), ('missing_finish', 'attempt_not_finished'), ('invalid_finish', 'attempt_not_finished'),
    ('semantic', 'not_network_failure'), ('unknown', 'not_network_failure'), ('tools', 'insufficient_budget'),
    ('paused', 'not_failed')])
def test_admission_refuses_unsafe_checkpoint(workflow, mutation, reason):
    task, _, store, _, _, _ = workflow
    failed = ResearchAgent(store, timeout_context).step(task.user_id, task.id)
    if mutation == 'running': failed = failed.model_copy(update={'steps': (failed.steps[0].model_copy(update={'status': 'running'}),) + failed.steps[1:]})
    if mutation == 'missing_finish': failed = failed.model_copy(update={'steps': (failed.steps[0].model_copy(update={'finished_at': None}),) + failed.steps[1:]})
    if mutation == 'invalid_finish': failed = failed.model_copy(update={'steps': (failed.steps[0].model_copy(update={'finished_at': 'not a timestamp'}),) + failed.steps[1:]})
    if mutation in {'semantic', 'unknown'}:
        step = failed.steps[0].model_copy(update={'result': failed.steps[0].result.model_copy(update={'error_type': 'ValueError' if mutation == 'semantic' else 'RuntimeError'})})
        failed = failed.model_copy(update={'steps': (step,) + failed.steps[1:]})
    if mutation == 'tools': failed = failed.model_copy(update={'budget': TaskBudget(max_steps=len(task.steps))})
    if mutation == 'paused': failed = failed.model_copy(update={'status': 'paused'})
    assert retry_decision(failed).reason == reason
    with pytest.raises(TaskConflict): retry_candidate(failed)


def test_remaining_model_budget_must_cover_all_unfinished_paid_steps(workflow):
    task, _, store, _, _, context = workflow
    task = store.create(task.model_copy(update={'id': 'research-budget-test', 'budget': TaskBudget(max_model_calls=4)}))
    agent = ResearchAgent(store, context)
    for _ in range(3): task = agent.step(task.user_id, task.id)
    task = ResearchAgent(store, timeout_context).step(task.user_id, task.id)
    assert retry_decision(task).reason == 'insufficient_budget'


def test_missing_or_foreign_and_anonymous_cannot_retry(client, user_headers, admin_headers, stopped):
    _, failed, _ = stopped
    url = f'/api/v1/research-tasks/{failed.id}/retry'
    for headers, status in [(None, 401), (admin_headers, 404)]:
        assert client.get(url, headers=headers).status_code == status
        assert client.post(url, headers=headers, json={'expected_revision': failed.revision}).status_code == status


def test_source_changed_rejects_without_mutating_checkpoint(client, user_headers, stopped):
    owner, failed, store = stopped
    with SessionLocal() as db: path = db.get(Document, failed.sources[0].document_id).local_path
    Path(path).write_text('changed isolated fixture bytes', encoding='utf-8')
    url = f'/api/v1/research-tasks/{failed.id}/retry'
    assert client.get(url, headers=user_headers).status_code == 400
    assert client.post(url, headers=user_headers, json={'expected_revision': failed.revision}).status_code == 400
    assert store.load(owner, failed.id) == failed


def test_cas_allows_only_one_concurrent_retry(stopped):
    owner, failed, store = stopped
    def attempt():
        try: return runtime.retry_failed(owner, failed.id, expected_revision=failed.revision).status
        except TaskConflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ['conflict', 'pending']
    assert len(store.load(owner, failed.id).retry_events) == 1


def test_legacy_serialization_omits_empty_retry_history(workflow):
    task = workflow[0]
    assert 'retry_events' not in task.model_dump(mode='json')
    assert ResearchTask.model_validate_json(task.model_dump_json()) == task


def test_retry_keeps_successful_document_batches_and_claims(workflow):
    task, _, store, model, _, context = workflow
    task = store.create(task.model_copy(update={'id': 'retry-batches', 'schema_version': 'research-comparison-v2',
        'budget': TaskBudget(max_steps=13), 'steps': comparison_plan(task.sources, task.goal, version='research-comparison-v2')}))
    generate = model.generate
    def fail_last(operation, payload):
        if operation == 'verify' and payload['claims'][0]['document_id'] == task.sources[-1].document_id:
            model.calls.append({'operation': operation, 'status': 'failed', 'error_type': 'ReadTimeout'})
            raise httpx.ReadTimeout('offline fixture')
        return generate(operation, payload)
    model.generate = fail_last
    failed = finish(ResearchAgent(store, context), task)
    assert len(failed.verification_batches) == 2
    ready = retry_candidate(failed)
    assert ready.claims == failed.claims and ready.bundles == failed.bundles
    assert ready.verification_batches == failed.verification_batches
    assert ready.steps[:8] == failed.steps[:8]
