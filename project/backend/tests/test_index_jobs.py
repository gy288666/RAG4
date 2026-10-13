"""Durable preparation contracts; no online index side effects."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.chunking import ChunkingConfig
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.index_job import DocumentIndexJob, StoredChunkSet
from app.services import document_service, index_job_service as jobs, parser_service, vector_store
from test_chunking_integration import upload


@pytest.fixture
def prepared(client, user_headers):
    return upload(client, user_headers, name="paper.md", text="# Title\n\nBody sentence. " * 100)


def test_durable_parents_and_idempotency(prepared):
    doc, user, _ = prepared
    before = vector_store.get_vector_store().count(user)
    job = jobs.create_job(user, doc, idempotency_key="first")
    assert job.status == "pending" and job.kind == "prepare_chunks"
    assert jobs.create_job(user, doc, idempotency_key="first").id == job.id
    done = jobs.run_job(user, job.id)
    assert done.status == "succeeded" and done.duration_ms >= 0
    assert done.started_at and done.finished_at and not done.error_code
    chunks = jobs.load_chunk_set(user, done.chunk_set_id)
    assert chunks.verify() and chunks.parent_chunks and chunks.child_chunks
    assert all(c.parent_chunk_id in {p.chunk_id for p in chunks.parent_chunks} for c in chunks.child_chunks)
    assert jobs.run_job(user, job.id).finished_at == done.finished_at
    second = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="second").id)
    assert second.chunk_set_id == done.chunk_set_id
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StoredChunkSet)) == 1
        assert db.get(Document, doc).status == "ready"
    assert vector_store.get_vector_store().count(user) == before


def test_changed_version_and_conflicting_key(prepared):
    doc, user, _ = prepared
    a = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="a").id)
    config = ChunkingConfig(chunking_version="v2")
    with pytest.raises(ValueError, match="conflicts"):
        jobs.create_job(user, doc, idempotency_key="a", config=config)
    b = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="b", config=config).id)
    assert a.chunk_set_id != b.chunk_set_id
    assert jobs.load_chunk_set(user, a.chunk_set_id).chunking_version != "v2"
    assert jobs.load_chunk_set(user, b.chunk_set_id).chunking_version == "v2"


@pytest.mark.parametrize("failure", ["source", "parser", "empty", "publication"])
def test_failures_preserve_ready_document_and_previous_snapshot(prepared, monkeypatch, failure):
    doc, user, _ = prepared
    old = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="old").id)
    before = vector_store.get_vector_store().count(user)
    new = jobs.create_job(user, doc, idempotency_key="new", config=ChunkingConfig(chunking_version="new"))
    if failure == "source":
        with SessionLocal() as db:
            Path(db.get(Document, doc).local_path).write_text("modified", encoding="utf-8")
    elif failure == "parser":
        def fail(*args, **kwargs):
            raise RuntimeError("secret-provider-token")
        monkeypatch.setattr(parser_service, "parse", fail)
    elif failure == "empty":
        monkeypatch.setattr(parser_service, "parse", lambda *a, **kw: parser_service.ParseResult([]))
    else:
        from sqlalchemy import event
        def fail_insert(*args):
            raise RuntimeError("storage unavailable")
        event.listen(StoredChunkSet, "before_insert", fail_insert)
    try:
        done = jobs.run_job(user, new.id)
    finally:
        if failure == "publication":
            event.remove(StoredChunkSet, "before_insert", fail_insert)
    assert done.status == "failed" and done.error_code and done.duration_ms >= 0
    assert "secret" not in done.error_code and done.chunk_set_id is None
    assert jobs.load_chunk_set(user, old.chunk_set_id).verify()
    with SessionLocal() as db:
        assert db.get(Document, doc).status == "ready"
        assert db.scalar(select(func.count()).select_from(StoredChunkSet)) == 1
    assert vector_store.get_vector_store().count(user) == before


def test_owner_isolation_and_corruption(prepared):
    doc, user, _ = prepared
    job = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="a").id)
    for operation in (
        lambda: jobs.create_job(user + 1, doc, idempotency_key="b"),
        lambda: jobs.get_job(user + 1, job.id),
        lambda: jobs.run_job(user + 1, job.id),
        lambda: jobs.load_chunk_set(user + 1, job.chunk_set_id),
    ):
        with pytest.raises(LookupError):
            operation()
    with SessionLocal() as db:
        row = db.get(StoredChunkSet, job.chunk_set_id)
        row.payload_json = row.payload_json.replace("Body sentence", "Tampered text")
        db.commit()
    with pytest.raises(ValueError):
        jobs.load_chunk_set(user, job.chunk_set_id)


def test_concurrent_claim_executes_parser_once(prepared, monkeypatch):
    import threading
    doc, user, _ = prepared
    job = jobs.create_job(user, doc, idempotency_key="a")
    entered, release = threading.Event(), threading.Event()
    original = parser_service.parse
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(parser_service, "parse", slow)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(jobs.run_job, user, job.id)
        try:
            assert entered.wait(10)
            assert jobs.run_job(user, job.id).status == "running"
        finally:
            release.set()
        assert first.result().status == "succeeded"


def test_delete_cleans_preparation_records(prepared):
    doc, user, _ = prepared
    job = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key="a").id)
    with SessionLocal() as db:
        document_service.delete_document(db, db.get(Document, doc))
        assert db.get(DocumentIndexJob, job.id) is None
        assert db.get(StoredChunkSet, job.chunk_set_id) is None
    with pytest.raises(LookupError):
        jobs.load_chunk_set(user, job.chunk_set_id)


def test_concurrent_creation_reuses_request(prepared):
    doc, user, _ = prepared
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: jobs.create_job(user, doc, idempotency_key="same"), range(2)))
    assert results[0].id == results[1].id
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DocumentIndexJob)) == 1


@pytest.mark.parametrize("key", ["", " ", "x" * 65, None])
def test_invalid_key(prepared, key):
    doc, user, _ = prepared
    with pytest.raises(ValueError):
        jobs.create_job(user, doc, idempotency_key=key)
