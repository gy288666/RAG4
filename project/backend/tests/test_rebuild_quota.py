"""Admission quota is transactional, owner-scoped and compatible with replay."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import threading

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.models.index_rebuild import IndexRebuild
from app.models.rebuild_request import RebuildRequest
from app.models.usage_log import UsageLog
from app.models.user import User
from app.services import index_rebuild_service as rebuilds, index_version_service as versions
from test_rebuild_api import corpus, BASE
from test_rebuild_idempotency import spec


@pytest.fixture(autouse=True)
def small_quota(monkeypatch):
    monkeypatch.setattr(settings, "RAG4_MAX_OPEN_REBUILDS_PER_USER", 1)


def test_quota_http_rejection_and_replay(client, user_headers, corpus):
    user = corpus[1]
    before = versions.active_state(user)
    body = {"dimension": 3, "idempotency_key": "first"}
    first = client.post(BASE, headers=user_headers, json=body).json()["data"]
    assert client.post(BASE, headers=user_headers, json=body).json()["data"]["id"] == first["id"]
    rejected = client.post(BASE, headers=user_headers, json={"dimension": 3, "idempotency_key": "second"})
    assert rejected.status_code == 429
    assert "配额" in rejected.json()["message"]
    assert client.post(BASE, headers=user_headers, json={**body, "dimension": 4}).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IndexRebuild)) == 1
        assert db.scalar(select(func.count()).select_from(RebuildRequest)) == 1
        logs = list(db.scalars(select(UsageLog).where(UsageLog.event_type == "index_rebuild_create")))
        assert len(logs) == 4 and sum(not log.is_success for log in logs) == 2
        assert all(log.duration_ms >= 0 for log in logs)
    assert versions.active_state(user) == before


@pytest.mark.parametrize("status", ["pending", "running", "failed"])
def test_retryable_states_consume_quota(corpus, status):
    user = corpus[1]
    task = rebuilds.create_rebuild(user, spec())
    with SessionLocal() as db:
        db.get(IndexRebuild, task.id).status = status
        db.commit()
    with pytest.raises(rebuilds.RebuildQuotaExceeded) as error:
        rebuilds.create_rebuild(user, spec())
    assert error.value.limit == error.value.open_count == 1
    assert rebuilds.list_rebuilds(user)[1] == 1


@pytest.mark.parametrize("status", ["ready", "cancelled"])
def test_terminal_states_release_without_deleting_history(corpus, status):
    user = corpus[1]
    first = rebuilds.create_rebuild(user, spec(), idempotency_key="old")
    with SessionLocal() as db:
        db.get(IndexRebuild, first.id).status = status
        db.commit()
    new = rebuilds.create_rebuild(user, spec(), idempotency_key="new")
    assert new.id != first.id and rebuilds.list_rebuilds(user)[1] == 2
    assert rebuilds.create_rebuild(user, spec(), idempotency_key="old").status == status


def test_running_cancel_does_not_release_until_worker_stops(corpus):
    user = corpus[1]
    task = rebuilds.create_rebuild(user, spec())
    with SessionLocal() as db:
        db.get(IndexRebuild, task.id).status = "running"
        db.commit()
    assert rebuilds.cancel_rebuild(user, task.id).status == "running"
    with pytest.raises(rebuilds.RebuildQuotaExceeded):
        rebuilds.create_rebuild(user, spec())


def test_recovery_transfers_capacity_and_preserves_original_key(corpus):
    user = corpus[1]
    first = rebuilds.create_rebuild(user, spec(), idempotency_key="recover")
    with SessionLocal() as db:
        db.get(IndexRebuild, first.id).status = "running"
        db.commit()
    successor = rebuilds.recover_rebuild(user, first.id)
    assert successor.status == "pending"
    assert rebuilds.recover_rebuild(user, first.id).id == successor.id
    assert rebuilds.create_rebuild(user, spec(), idempotency_key="recover").status == "cancelled"
    with pytest.raises(rebuilds.RebuildQuotaExceeded):
        rebuilds.create_rebuild(user, spec())
    rebuilds.cancel_rebuild(user, successor.id)
    assert rebuilds.create_rebuild(user, spec()).status == "pending"


def test_users_have_independent_quota_without_account_timestamp_mutation(corpus, monkeypatch):
    with SessionLocal() as db:
        other = User(email="quota-other@example.invalid", password_hash="not-a-login-hash")
        db.add(other)
        db.get(User, corpus[1]).updated_at = datetime(2000, 1, 1)
        db.commit()
        other_id = other.id
        before = db.get(User, corpus[1]).updated_at
    monkeypatch.setattr(rebuilds, "_sources", lambda user: [{"id": "synthetic", "name": "paper", "sha256": "x"}])
    first = rebuilds.create_rebuild(corpus[1], spec())
    second = rebuilds.create_rebuild(other_id, spec())
    assert first.id != second.id
    with SessionLocal() as db:
        assert db.get(User, corpus[1]).updated_at == before


def test_parallel_distinct_requests_cannot_overbook(corpus, monkeypatch):
    monkeypatch.setattr(settings, "RAG4_MAX_OPEN_REBUILDS_PER_USER", 2)
    barrier = threading.Barrier(4)
    original = rebuilds._sources
    def sources(user):
        result = original(user)
        barrier.wait(timeout=20)
        return result
    monkeypatch.setattr(rebuilds, "_sources", sources)
    def create(key):
        try:
            return rebuilds.create_rebuild(corpus[1], spec(), idempotency_key=key).id
        except rebuilds.RebuildQuotaExceeded:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(create, ["a", "b", "c", "d"]))
    assert len({value for value in ids if value is not None}) == 2
    assert ids.count(None) == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IndexRebuild)) == 2
        assert db.scalar(select(func.count()).select_from(RebuildRequest)) == 2


def test_parallel_same_key_replay_works_at_capacity(corpus, monkeypatch):
    barrier = threading.Barrier(2)
    original = rebuilds._sources
    def sources(user):
        result = original(user)
        barrier.wait(timeout=20)
        return result
    monkeypatch.setattr(rebuilds, "_sources", sources)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(rebuilds.create_rebuild, corpus[1], spec(), idempotency_key="same") for _ in range(2)]
        ids = [future.result(timeout=30).id for future in futures]
    assert ids[0] == ids[1] and rebuilds.list_rebuilds(corpus[1])[1] == 1


def test_parallel_recovery_and_admission_cannot_overbook(corpus, monkeypatch):
    user = corpus[1]
    first = rebuilds.create_rebuild(user, spec())
    with SessionLocal() as db:
        db.get(IndexRebuild, first.id).status = "running"
        db.commit()
    barrier = threading.Barrier(2)
    original = rebuilds._lock_rebuild_owner
    def lock(db, owner):
        barrier.wait(timeout=20)
        return original(db, owner)
    monkeypatch.setattr(rebuilds, "_lock_rebuild_owner", lock)
    def create():
        with pytest.raises(rebuilds.RebuildQuotaExceeded):
            rebuilds.create_rebuild(user, spec())
    with ThreadPoolExecutor(max_workers=2) as pool:
        admission = pool.submit(create)
        recovery = pool.submit(rebuilds.recover_rebuild, user, first.id)
        admission.result(timeout=30)
        successor = recovery.result(timeout=30)
    assert successor.status == "pending" and rebuilds.list_rebuilds(user)[1] == 2


def test_lowered_quota_blocks_new_tasks_but_allows_recovery(corpus, monkeypatch):
    user = corpus[1]
    monkeypatch.setattr(settings, "RAG4_MAX_OPEN_REBUILDS_PER_USER", 2)
    first = rebuilds.create_rebuild(user, spec())
    rebuilds.create_rebuild(user, spec())
    with SessionLocal() as db:
        db.get(IndexRebuild, first.id).status = "running"
        db.commit()
    monkeypatch.setattr(settings, "RAG4_MAX_OPEN_REBUILDS_PER_USER", 1)
    assert rebuilds.recover_rebuild(user, first.id).status == "pending"
    with pytest.raises(rebuilds.RebuildQuotaExceeded) as error:
        rebuilds.create_rebuild(user, spec())
    assert error.value.limit == 1 and error.value.open_count == 2


def test_rolled_back_creation_does_not_consume_quota(corpus):
    def fail(*args):
        raise RuntimeError("injected mapping failure")
    event.listen(RebuildRequest, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            rebuilds.create_rebuild(corpus[1], spec(), idempotency_key="atomic")
    finally:
        event.remove(RebuildRequest, "before_insert", fail)
    assert rebuilds.create_rebuild(corpus[1], spec(), idempotency_key="atomic").status == "pending"


@pytest.mark.parametrize("limit", [0, -1, 10001])
def test_invalid_quota_configuration_fails_at_startup(limit):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RAG4_MAX_OPEN_REBUILDS_PER_USER=limit)
