"""Interrupted execution recovery is fenced, atomic and checkpoint preserving."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, select

from app.core.database import SessionLocal
from app.models.rebuild_recovery import RebuildRecovery
from app.services import index_rebuild_service as batches, index_build_service as builds
from app.services import index_version_service as versions
from test_chunking_integration import storage
from test_index_versions import complete
from test_index_rebuilds import make_task


class SimulatedCrash(BaseException):
    pass


def interrupt_after_first(complete, storage, monkeypatch):
    user, task = make_task(complete)
    original = builds.RemoteEmbeddingAdapter.embed_documents
    calls = []
    def crash(self, texts):
        calls.append(texts)
        if len(calls) == 2:
            raise SimulatedCrash()
        return original(self, texts)
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", crash)
    with pytest.raises(SimulatedCrash):
        batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert batches.get_rebuild(user, task.id).status == "running"
    return user, task, calls


def test_crash_recovery_reuses_committed_checkpoint(complete, storage, monkeypatch):
    user, task, calls = interrupt_after_first(complete, storage, monkeypatch)
    successor = batches.recover_rebuild(user, task.id)
    assert successor.id != task.id and successor.base_revision == task.base_revision
    assert len(json.loads(successor.checkpoints_json)) == 1
    assert batches.get_rebuild(user, task.id).status == "cancelled"
    assert batches.recover_rebuild(user, task.id).id == successor.id
    done = batches.run_rebuild(user, successor.id, api_key="secret", store=storage)
    assert done.status == "ready" and len(calls) == 3
    assert batches.run_rebuild(user, task.id, api_key="secret", store=storage).status == "cancelled"
    assert versions.active_state(user) == (None, 0)


def test_late_old_worker_cannot_publish_successor(complete, storage, monkeypatch):
    user, task = make_task(complete)
    original = builds.RemoteEmbeddingAdapter.embed_documents
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow(self, texts):
        calls.append(texts)
        if len(calls) == 2:
            entered.set()
            assert release.wait(30)
        return original(self, texts)
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", slow)
    with ThreadPoolExecutor(max_workers=1) as executor:
        old = executor.submit(batches.run_rebuild, user, task.id, api_key="secret", store=storage)
        try:
            assert entered.wait(30)
            successor = batches.recover_rebuild(user, task.id)
            done = batches.run_rebuild(user, successor.id, api_key="secret", store=storage)
            assert done.status == "ready"
            saved = done.checkpoints_json
        finally:
            release.set()
        assert old.result().status == "cancelled"
    assert batches.get_rebuild(user, successor.id).checkpoints_json == saved
    assert batches.get_rebuild(user, task.id).version_id is None


def test_concurrent_recovery_has_one_successor(complete, storage, monkeypatch):
    user, task, _ = interrupt_after_first(complete, storage, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: batches.recover_rebuild(user, task.id), range(2)))
    assert results[0].id == results[1].id
    with SessionLocal() as db:
        assert len(db.scalars(select(RebuildRecovery)).all()) == 1


def test_recovery_transaction_failure_keeps_original_running(complete, storage, monkeypatch):
    user, task, _ = interrupt_after_first(complete, storage, monkeypatch)
    def fail(*args):
        raise RuntimeError("recovery audit unavailable")
    event.listen(RebuildRecovery, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            batches.recover_rebuild(user, task.id)
    finally:
        event.remove(RebuildRecovery, "before_insert", fail)
    old = batches.get_rebuild(user, task.id)
    assert old.status == "running" and not old.cancel_requested
    with SessionLocal() as db:
        assert db.scalar(select(RebuildRecovery)) is None


def test_recovery_permissions_and_intentional_cancel(complete, storage, monkeypatch):
    user, task, _ = interrupt_after_first(complete, storage, monkeypatch)
    with pytest.raises(LookupError):
        batches.recover_rebuild(user + 1, task.id)
    batches.cancel_rebuild(user, task.id)
    with pytest.raises(ValueError):
        batches.recover_rebuild(user, task.id)
    user, pending = make_task(complete)
    with pytest.raises(ValueError):
        batches.recover_rebuild(user, pending.id)
