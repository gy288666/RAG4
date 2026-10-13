from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlalchemy import event, func, select

from app.core.database import SessionLocal
from app.models.index_rebuild import IndexRebuild
from app.models.rebuild_request import RebuildRequest
from app.services import index_rebuild_service as rebuilds
from app.services.index_build_service import EmbeddingSpec
from test_rebuild_api import corpus, BASE


def spec(dimension=3):
    return EmbeddingSpec(endpoint="https://configured.invalid/v1/embeddings", model_id="configured-model",
                         version="configured-v1", dimension=dimension)


def test_replay_keeps_original_even_after_cancellation_and_source_change(corpus, monkeypatch):
    user = corpus[1]
    first = rebuilds.create_rebuild(user, spec(), idempotency_key="request-1")
    rebuilds.cancel_rebuild(user, first.id)
    monkeypatch.setattr(rebuilds, "_sources", lambda user: pytest.fail("replay must not resnapshot"))
    replay = rebuilds.create_rebuild(user, spec(), idempotency_key="request-1")
    assert replay.id == first.id and replay.status == "cancelled"
    assert replay.request_json == first.request_json and replay.base_revision == first.base_revision


def test_api_replay_and_conflict(client, user_headers, corpus):
    body = {"dimension": 3, "idempotency_key": "api-key"}
    first = client.post(BASE, headers=user_headers, json=body)
    assert first.status_code == 200
    assert client.post(BASE, headers=user_headers, json=body).json()["data"]["id"] == first.json()["data"]["id"]
    body["dimension"] = 4
    assert client.post(BASE, headers=user_headers, json=body).status_code == 409
    assert rebuilds.list_rebuilds(corpus[1])[1] == 1


def test_concurrent_first_creation_rolls_back_loser(corpus, monkeypatch):
    barrier = threading.Barrier(2)
    original = rebuilds._sources
    def sources(user):
        value = original(user)
        barrier.wait(timeout=15)
        return value
    monkeypatch.setattr(rebuilds, "_sources", sources)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(rebuilds.create_rebuild, corpus[1], spec(), idempotency_key="race") for _ in range(2)]
        ids = [f.result(timeout=20).id for f in futures]
    assert ids[0] == ids[1]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(IndexRebuild)) == 1
        assert db.scalar(select(func.count()).select_from(RebuildRequest)) == 1


def test_mapping_failure_rolls_back_task(corpus):
    def fail(*args):
        raise RuntimeError("injected mapping failure")
    event.listen(RebuildRequest, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            rebuilds.create_rebuild(corpus[1], spec(), idempotency_key="atomic")
    finally:
        event.remove(RebuildRequest, "before_insert", fail)
    assert rebuilds.list_rebuilds(corpus[1])[1] == 0


def test_owner_and_case_sensitive_key_scope(corpus, monkeypatch):
    from app.models.user import User
    user = corpus[1]
    with SessionLocal() as db:
        other = User(email="other-idempotency@example.invalid", password_hash="not-a-login-hash")
        db.add(other)
        db.commit()
        other_id = other.id
    # No execution: a synthetic frozen corpus suffices to test key ownership.
    monkeypatch.setattr(rebuilds, "_sources", lambda user: [{"id": "synthetic", "name": "paper", "sha256": "x"}])
    ids = {rebuilds.create_rebuild(owner, spec(), idempotency_key=key).id
           for owner, key in [(user, "KEY"), (user, "key"), (other_id, "KEY")]}
    assert len(ids) == 3


@pytest.mark.parametrize("key", ["", " leading", "trailing ", "a" * 65, "中文"])
def test_invalid_key_does_not_create(corpus, key):
    with pytest.raises(ValueError):
        rebuilds.create_rebuild(corpus[1], spec(), idempotency_key=key)
    assert rebuilds.list_rebuilds(corpus[1])[1] == 0


def test_legacy_without_key_still_creates_distinct_tasks(corpus):
    assert rebuilds.create_rebuild(corpus[1], spec()).id != rebuilds.create_rebuild(corpus[1], spec()).id


def test_recovery_does_not_rebind_original_creation_key(corpus):
    user = corpus[1]
    first = rebuilds.create_rebuild(user, spec(), idempotency_key="recover-original")
    with SessionLocal() as db:
        db.get(IndexRebuild, first.id).status = "running"
        db.commit()
    successor = rebuilds.recover_rebuild(user, first.id)
    replay = rebuilds.create_rebuild(user, spec(), idempotency_key="recover-original")
    assert replay.id == first.id and replay.status == "cancelled"
    assert successor.id != first.id and successor.status == "pending"
