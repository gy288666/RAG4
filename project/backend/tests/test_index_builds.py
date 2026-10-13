"""Candidate validation using real Local/Chroma stores and deterministic model IO."""

import json
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.index_build import IndexBuild
from app.services import index_build_service as builds, index_job_service as jobs, document_service
from app.services.vector_store import VectorRecord
from test_chunking_integration import storage, upload


@pytest.fixture
def candidate(client, user_headers, storage, monkeypatch):
    doc, user, _ = upload(client, user_headers, text="Retrieval finds evidence. " * 45)
    prepared = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="prepare").id)
    class FakeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def embed_documents(self, texts):
            return [[1.0, float(i + 1), 0.5] for i, _ in enumerate(texts)]
    monkeypatch.setattr(builds, "RemoteEmbeddingAdapter", FakeAdapter)
    spec = builds.EmbeddingSpec(endpoint="https://model.example/v1/embeddings", model_id="test-model",
                                version="revision-1", dimension=3)
    row = builds.create_build(user, prepared.chunk_set_id, spec, idempotency_key="build")
    return doc, user, row, spec


def test_build_validates_without_changing_live_index(candidate, storage):
    doc, user, row, spec = candidate
    before = storage.read_records(user, index_version="baseline")
    done = builds.run_build(user, row.id, api_key="secret", store=storage)
    assert done.status == "validated" and done.duration_ms >= 0
    manifest = json.loads(done.manifest_json)
    records = storage.read_records(user, index_version=done.index_version)
    chunks = jobs.load_chunk_set(user, row.chunk_set_id)
    assert len(records) == manifest["record_count"] == len(chunks.child_chunks)
    assert manifest["embedding"] == spec.model_dump() and manifest["dimension"] == 3
    assert {r.id for r in records} == {c.chunk_id for c in chunks.child_chunks}
    assert storage.read_records(user, index_version="baseline") == before
    assert builds.run_build(user, row.id, api_key="unused", store=storage).finished_at == done.finished_at
    assert "secret" not in (done.embedding_spec_json + done.manifest_json)
    with SessionLocal() as db:
        assert db.get(Document, doc).status == "ready"


@pytest.mark.parametrize("fault", ["count", "dimension", "nan", "zero", "exception"])
def test_invalid_embedding_never_writes(candidate, storage, monkeypatch, fault):
    doc, user, row, spec = candidate
    def bad(self, texts):
        if fault == "exception":
            raise RuntimeError("sensitive-provider-response")
        vectors = [[1.0, 2.0, 3.0] for _ in texts]
        if fault == "count":
            return vectors[:-1]
        vectors[0] = {"dimension": [1.0], "nan": [float("nan"), 1, 2], "zero": [0, 0, 0]}[fault]
        return vectors
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", bad)
    done = builds.run_build(user, row.id, api_key="secret", store=storage)
    assert done.status == "failed" and done.error_stage == "embedding"
    assert done.manifest_json is None and "sensitive" not in done.error_code
    assert storage.read_records(user, index_version=row.index_version) == []


@pytest.mark.parametrize("fault", ["partial", "metadata", "vector", "extra", "write_exception"])
def test_write_and_readback_failures_stay_isolated(candidate, storage, monkeypatch, fault):
    doc, user, row, spec = candidate
    before = storage.read_records(user, index_version="baseline")
    original = storage.add
    def broken(user_id, records, *, index_version):
        if fault in {"partial", "write_exception"}:
            records = records[:1]
        elif fault == "metadata":
            records = [replace(records[0], doc_id="wrong-owner-source"), *records[1:]]
        elif fault == "vector":
            records = [replace(records[0], embedding=[9.0, 8.0, 7.0]), *records[1:]]
        else:
            records = [*records, replace(records[0], id="unexpected-id")]
        original(user_id, records, index_version=index_version)
        if fault == "write_exception":
            raise RuntimeError("write interrupted")
    monkeypatch.setattr(storage, "add", broken)
    done = builds.run_build(user, row.id, api_key="secret", store=storage)
    assert done.status == "failed" and done.manifest_json is None
    assert done.error_stage == ("write" if fault == "write_exception" else "verify")
    assert storage.read_records(user, index_version="baseline") == before
    monkeypatch.setattr(storage, "add", original)
    retry = builds.create_build(user, row.chunk_set_id, spec, idempotency_key="retry")
    assert retry.index_version != row.index_version
    assert builds.run_build(user, retry.id, api_key="secret", store=storage).status == "validated"


def test_idempotency_and_permissions(candidate, storage):
    doc, user, row, spec = candidate
    assert builds.create_build(user, row.chunk_set_id, spec, idempotency_key="build").id == row.id
    with pytest.raises(ValueError):
        builds.create_build(user, row.chunk_set_id, spec.model_copy(update={"version": "v2"}), idempotency_key="build")
    for operation in (
        lambda: builds.create_build(user + 1, row.chunk_set_id, spec, idempotency_key="build"),
        lambda: builds.get_build(user + 1, row.id),
        lambda: builds.run_build(user + 1, row.id, api_key="secret", store=storage),
    ):
        with pytest.raises(LookupError):
            operation()


def test_claim_once_and_delete_cleans_candidates(candidate, storage, monkeypatch):
    doc, user, row, spec = candidate
    entered, release = threading.Event(), threading.Event()
    original = builds.RemoteEmbeddingAdapter.embed_documents
    def slow(self, texts):
        entered.set()
        assert release.wait(10)
        return original(self, texts)
    monkeypatch.setattr(builds.RemoteEmbeddingAdapter, "embed_documents", slow)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(builds.run_build, user, row.id, api_key="secret", store=storage)
        try:
            assert entered.wait(10)
            assert builds.run_build(user, row.id, api_key="secret", store=storage).status == "running"
        finally:
            release.set()
        assert future.result().status == "validated"
    with SessionLocal() as db:
        document_service.delete_document(db, db.get(Document, doc))
        assert db.get(IndexBuild, row.id) is None
    assert storage.read_records(user, index_version=row.index_version) == []


def test_existing_namespace_is_not_overwritten(candidate, storage):
    _, user, row, _ = candidate
    record = VectorRecord(id="occupied", text="Keep me", embedding=[1., 2., 3.], doc_id=row.document_id,
                          user_id=user, file_name="x", chunk_index=0)
    storage.add(user, [record], index_version=row.index_version)
    done = builds.run_build(user, row.id, api_key="secret", store=storage)
    assert done.status == "failed" and done.error_stage == "load"
    assert storage.read_records(user, index_version=row.index_version) == [record]


def test_sql_publication_failure_does_not_validate(candidate, storage):
    from sqlalchemy import event
    _, user, row, _ = candidate
    before = storage.read_records(user, index_version="baseline")
    def fail_publication(mapper, connection, target):
        if target.status == "validated":
            raise RuntimeError("simulated transaction failure")
    event.listen(IndexBuild, "before_update", fail_publication)
    try:
        done = builds.run_build(user, row.id, api_key="secret", store=storage)
    finally:
        event.remove(IndexBuild, "before_update", fail_publication)
    assert done.status == "failed" and done.error_stage == "publish"
    assert done.manifest_json is None
    assert storage.read_records(user, index_version="baseline") == before


@pytest.mark.parametrize("endpoint", ["https://user:password@example.com", "https://example.com?k=secret", "file:///x"])
def test_spec_rejects_credential_urls(endpoint):
    with pytest.raises(ValueError):
        builds.EmbeddingSpec(endpoint=endpoint, model_id="m", version="v", dimension=3)
