"""A stale browser action cannot consume another step or another model attempt."""
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.research.agent import ResearchAgent, TaskConflict
from test_research_agent import workflow
from test_research_runtime import published, storage


def test_sequential_duplicate_revision_cannot_execute_second_step(workflow):
    task, _, store, model, agent, _ = workflow
    done = agent.step(task.user_id, task.id, expected_revision=task.revision)
    before = store.load(task.user_id, task.id)
    assert done.tool_calls_used == 1
    with pytest.raises(TaskConflict):
        agent.step(task.user_id, task.id, expected_revision=task.revision)
    assert store.load(task.user_id, task.id) == before
    assert model.calls == []


def test_concurrent_duplicate_is_fenced_before_context(workflow):
    task, _, store, _, _, context = workflow
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow_context(current):
        calls.append(current.id)
        entered.set()
        assert release.wait(10)
        return context(current)
    agent = ResearchAgent(store, slow_context)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(agent.step, task.user_id, task.id, expected_revision=0)
        try:
            assert entered.wait(10)
            with pytest.raises(TaskConflict):
                agent.step(task.user_id, task.id, expected_revision=0)
        finally:
            release.set()
        assert first.result().tool_calls_used == 1
    assert calls == [task.id]


def test_control_still_fences_late_execution_result(workflow):
    task, _, store, _, _, context = workflow
    entered, release = threading.Event(), threading.Event()
    def slow_context(current):
        entered.set()
        assert release.wait(10)
        return context(current)
    agent = ResearchAgent(store, slow_context)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(agent.step, task.user_id, task.id, expected_revision=0)
        try:
            assert entered.wait(10)
            running = store.load(task.user_id, task.id)
            cancelled = agent.control(task.user_id, task.id, 'cancel', running.revision)
        finally:
            release.set()
        assert first.result() == cancelled
    assert store.load(task.user_id, task.id).status == 'cancelled'


def test_http_expected_revision_and_legacy_no_body(client, user_headers, published):
    owner, task, _, _ = published
    url = f'/api/v1/research-tasks/{task.id}/run'
    assert client.post(url, headers=user_headers, json={'expected_revision': 0}).status_code == 200
    assert client.post(url, headers=user_headers, json={'expected_revision': 0}).status_code == 409
    assert client.post(url, headers=user_headers).status_code == 200


@pytest.mark.parametrize('body', [{}, {'expected_revision': True}, {'expected_revision': -1}, {'expected_revision': '0'}, {'expected_revision': 0, 'extra': 1}])
def test_http_invalid_revision_never_claims(client, user_headers, published, body):
    owner, task, _, _ = published
    assert client.post(f'/api/v1/research-tasks/{task.id}/run', headers=user_headers, json=body).status_code == 400
    from app.research.store import SQLResearchTaskStore
    assert SQLResearchTaskStore().load(owner, task.id) == task
