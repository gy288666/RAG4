from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from app.core.database import SessionLocal
from app.models.user import User
from app.services import index_build_service as builds, index_rebuild_service as rebuilds
from app.services import index_version_service as versions
from app.services.rebuild_execution import execute_configured_rebuild
from test_rebuild_api import corpus, create


@pytest.fixture
def ready_task(client, user_headers, corpus, monkeypatch):
    corpus[2].embedding_api_key = "configured-secret"
    calls = []
    class Model:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def embed_documents(self, texts):
            return [[1., 2., 3.] for _ in texts]
    monkeypatch.setattr(builds, "RemoteEmbeddingAdapter", Model)
    task = create(client, user_headers)
    return corpus[1], task["id"], corpus[2], calls, Model


def test_execute_and_replay_preserve_active(ready_task):
    user, task, config, calls, _ = ready_task
    before = versions.active_state(user)
    result = execute_configured_rebuild(user, task)
    assert result.status == "ready" and result.attempt == 1 and result.version_id
    assert calls and "configured-secret" in str(calls)
    assert "configured-secret" not in result.request_json
    config.embedding_api_key = ""
    assert execute_configured_rebuild(user, task).version_id == result.version_id
    assert len(calls) == 1 and versions.active_state(user) == before


@pytest.mark.parametrize("field,value", [("embedding_base_url", "https://other.invalid"),
    ("embedding_model", "other"), ("embedding_version", "other"), ("embedding_provider", "local"),
    ("embedding_api_key", " ")])
def test_config_drift_rejected_before_claim(ready_task, field, value):
    user, task, config, calls, _ = ready_task
    setattr(config, field, value)
    with pytest.raises(ValueError):
        execute_configured_rebuild(user, task)
    assert not calls
    row = rebuilds.get_rebuild(user, task)
    assert row.status == "pending" and row.attempt == 0


def test_wrong_owner_and_disabled_user_cannot_execute(ready_task):
    user, task, _, calls, _ = ready_task
    with pytest.raises(LookupError):
        execute_configured_rebuild(user + 1, task)
    with SessionLocal() as db:
        db.get(User, user).status = 0
        db.commit()
    with pytest.raises(PermissionError):
        execute_configured_rebuild(user, task)
    assert not calls


def test_failed_execution_retries_without_activating(ready_task, monkeypatch):
    user, task, _, _, model = ready_task
    original = model.embed_documents
    def fail(*args):
        raise RuntimeError("private model failure")
    monkeypatch.setattr(model, "embed_documents", fail)
    result = execute_configured_rebuild(user, task)
    assert result.status == "failed" and result.attempt == 1
    monkeypatch.setattr(model, "embed_documents", original)
    assert execute_configured_rebuild(user, task).status == "ready"
    assert rebuilds.get_rebuild(user, task).attempt == 2
    assert versions.active_state(user) == (None, 0)


def test_duplicate_workers_do_not_embed_twice(ready_task, monkeypatch):
    user, task, _, calls, model = ready_task
    entered, release = threading.Event(), threading.Event()
    original = model.embed_documents
    def blocked(self, texts):
        entered.set()
        assert release.wait(15)
        return original(self, texts)
    monkeypatch.setattr(model, "embed_documents", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute_configured_rebuild, user, task)
        try:
            assert entered.wait(15)
            assert execute_configured_rebuild(user, task).status == "running"
        finally:
            release.set()
        assert first.result().status == "ready"
    assert len(calls) == 1


def test_cli_refuses_implicit_database(monkeypatch, capsys):
    from scripts.run_index_rebuild import main
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["worker", "--user-id", "1", "--task-id", "task"])
    assert main() == 2
    assert "explicit_database_required" in capsys.readouterr().out
