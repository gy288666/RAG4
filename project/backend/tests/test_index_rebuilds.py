"""Batch progress, retry, cancellation and explicit guarded activation."""
import json
from pathlib import Path

import pytest

from app.core.database import SessionLocal
from app.models.document import Document
from app.services import index_rebuild_service as batches, index_build_service as builds
from app.services import index_version_service as versions
from test_chunking_integration import storage, upload
from test_index_versions import complete


def make_task(complete):
    user, ids, _, _, _ = complete
    spec = builds.EmbeddingSpec.model_validate_json(builds.get_build(user, ids[0]).embedding_spec_json)
    return user, batches.create_rebuild(user, spec)


def test_batch_version_is_not_automatically_activated(complete, storage):
    user, task = make_task(complete)
    done = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert done.status == "ready" and len(json.loads(done.checkpoints_json)) == 2
    assert versions.active_state(user) == (None, 0)
    versions.switch_version(user, done.version_id, expected_revision=done.base_revision, store=storage)
    assert versions.active_state(user)[0] == done.version_id
    assert batches.run_rebuild(user, task.id, api_key="unused", store=storage).attempt == 1


def test_retry_skips_checkpointed_document(complete, storage, monkeypatch):
    user, task = make_task(complete)
    original = builds.RemoteEmbeddingAdapter.embed_documents
    calls = []
    def fail_second(self, texts):
        calls.append(texts)
        if len(calls) == 2:
            raise RuntimeError("provider unavailable secret")
        return original(self, texts)
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", fail_second)
    failed = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert failed.status == "failed" and failed.error_document_id
    assert len(json.loads(failed.checkpoints_json)) == 1
    done = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert done.status == "ready" and done.attempt == 2 and len(calls) == 3
    assert failed.error_code == "RuntimeError" and done.error_code is None


def test_cancel_running_stops_at_boundary(complete, storage, monkeypatch):
    user, task = make_task(complete)
    original = builds.RemoteEmbeddingAdapter.embed_documents
    calls = []
    def cancel(self, texts):
        calls.append(texts)
        batches.cancel_rebuild(user, task.id)
        return original(self, texts)
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", cancel)
    done = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert done.status == "cancelled" and done.version_id is None and len(calls) == 1
    assert len(json.loads(done.checkpoints_json)) == 1
    assert batches.run_rebuild(user, task.id, api_key="secret", store=storage).attempt == 1
    assert versions.active_state(user) == (None, 0)


def test_source_change_fails_before_model(complete, storage, monkeypatch):
    user, task = make_task(complete)
    with SessionLocal() as db:
        path = db.get(Document, complete[2][0]).local_path
    Path(path).write_text("changed", encoding="utf-8")
    def forbidden(*args, **kwargs):
        pytest.fail("Changed source must not be embedded")
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", forbidden)
    done = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert done.status == "failed" and done.checkpoints_json == "{}"


def test_permission_and_pending_cancellation(complete, storage):
    user, task = make_task(complete)
    with pytest.raises(LookupError):
        batches.run_rebuild(user + 1, task.id, api_key="secret", store=storage)
    with pytest.raises(LookupError):
        batches.cancel_rebuild(user + 1, task.id)
    assert batches.cancel_rebuild(user, task.id).status == "cancelled"
    assert batches.run_rebuild(user, task.id, api_key="secret", store=storage).attempt == 0


def test_rebuild_after_upload_and_activation_revision_guard(complete, storage, client, user_headers):
    user, _, _, old, config = complete
    versions.switch_version(user, old.id, expected_revision=0, store=storage)
    upload(client, user_headers, name="added.txt", text="New synthetic evidence.")
    user, task = make_task(complete)
    done = batches.run_rebuild(user, task.id, api_key="secret", store=storage)
    assert done.status == "ready" and len(json.loads(done.checkpoints_json)) == 3
    versions.switch_version(user, None, expected_revision=1, store=storage)
    with pytest.raises(ValueError, match="revision"):
        versions.switch_version(user, done.version_id, expected_revision=done.base_revision, store=storage)
    versions.switch_version(user, done.version_id, expected_revision=2, store=storage)
    assert len({h.doc_id for h in versions.search_active(user, "evidence", config, store=storage)}) == 3
