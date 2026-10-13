"""Opt-in durable chunk preparation. Never writes vectors or document status.

Public methods require the authenticated owner ID. The persisted config and
source digest are frozen on creation; result publication and success share one
SQL transaction. Callers must not interpret succeeded as an active index.
"""

import hashlib
import time
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.chunking import ChunkingConfig, ChunkingEngine, ChunkSet
from app.chunking.adapter import adapt_parse_result
from app.core.database import session_scope
from app.models.document import Document
from app.models.index_job import DocumentIndexJob, StoredChunkSet
from app.services import parser_service
from app.utils.ids import generate_id


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _digest(path: str) -> str:
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _owned_document(db, user_id, document_id):
    document = db.get(Document, document_id)
    if document is None or document.user_id != user_id:
        raise LookupError("Document not found")
    return document


def get_job(user_id: int, job_id: str) -> DocumentIndexJob:
    """Return detached status/timing/config snapshot, scoped to document owner."""
    with session_scope() as db:
        job = db.get(DocumentIndexJob, job_id)
        if job is None or job.user_id != user_id:
            raise LookupError("Job not found")
        _owned_document(db, user_id, job.document_id)
        db.expunge(job)
        return job


def create_job(user_id: int, document_id: str, *, idempotency_key: str,
               config: ChunkingConfig | None = None) -> DocumentIndexJob:
    """Freeze a preparation request. Key reuse with another request is rejected."""
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 64 or not idempotency_key.strip():
        raise ValueError("idempotency_key must contain 1..64 characters")
    config_json = (config or ChunkingConfig()).model_dump_json()

    def existing(db):
        job = db.scalar(select(DocumentIndexJob).where(
            DocumentIndexJob.user_id == user_id,
            DocumentIndexJob.idempotency_key == idempotency_key,
        ))
        if job and (job.document_id != document_id or job.config_json != config_json):
            raise ValueError("Idempotency key conflicts with another request")
        return job

    try:
        with session_scope() as db:
            doc = _owned_document(db, user_id, document_id)
            job = existing(db)
            if job is None:
                job = DocumentIndexJob(
                    id=generate_id("idx"), user_id=user_id, document_id=document_id,
                    idempotency_key=idempotency_key, config_json=config_json,
                    source_sha256=_digest(doc.local_path),
                )
                db.add(job)
                db.flush()
            job_id = job.id
    except IntegrityError:
        # The unique constraint arbitrates simultaneous identical submissions.
        with session_scope() as db:
            job = existing(db)
            if job is None:
                raise
            job_id = job.id
    return get_job(user_id, job_id)


def run_job(user_id: int, job_id: str) -> DocumentIndexJob:
    """Claim once, prepare and atomically publish; repeated calls never rerun.

    Source changes fail closed. Parser/tokenizer versions are recorded in the
    resulting ChunkSet; no mutable model settings or credentials are stored.
    """
    job = get_job(user_id, job_id)
    with session_scope() as db:
        claimed = db.execute(update(DocumentIndexJob).where(
            DocumentIndexJob.id == job_id, DocumentIndexJob.status == "pending",
        ).values(status="running", started_at=_now())).rowcount
    if not claimed:
        return get_job(user_id, job_id)
    started = time.monotonic()
    try:
        with session_scope() as db:
            doc = _owned_document(db, user_id, job.document_id)
            path, name = doc.local_path, doc.file_name
        # Parse the exact bytes verified against the request, not a file that
        # another writer could replace between hashing and parsing.
        with tempfile.TemporaryDirectory(prefix="rag4_prepare_") as directory:
            snapshot = str(Path(directory) / ("source" + Path(name).suffix))
            shutil.copyfile(path, snapshot)
            if _digest(snapshot) != job.source_sha256:
                raise ValueError("source_changed")
            parsed = adapt_parse_result(parser_service.parse(snapshot, name, structured=True),
                                        document_id=job.document_id, file_name=name)
        chunks = ChunkingEngine().split(parsed, ChunkingConfig.model_validate_json(job.config_json))
        if not chunks.child_chunks or not chunks.verify(parsed):
            raise ValueError("invalid_chunk_set")
        payload = chunks.model_dump_json()
        with session_scope() as db:
            # Serialize publication for this document, including concurrent jobs.
            doc = db.scalar(select(Document).where(Document.id == job.document_id,
                            Document.user_id == user_id).with_for_update())
            if doc is None:
                raise LookupError("Document not found")
            stored = db.get(StoredChunkSet, chunks.chunk_set_id)
            if stored is None:
                db.add(StoredChunkSet(id=chunks.chunk_set_id, document_id=job.document_id, payload_json=payload))
            elif stored.payload_json != payload:
                raise ValueError("chunk_set_conflict")
            current = db.get(DocumentIndexJob, job_id)
            current.chunk_set_id = chunks.chunk_set_id
            current.status = "succeeded"
            current.finished_at = _now()
            current.duration_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:
        # Store bounded classification only: exception messages can contain paths,
        # source text or provider credentials. Expected failure codes are public.
        code = str(exc) if str(exc) in {"source_changed", "invalid_chunk_set", "chunk_set_conflict"} else type(exc).__name__
        with session_scope() as db:
            current = db.get(DocumentIndexJob, job_id)
            if current is not None:
                current.status = "failed"
                current.error_code = code[:64]
                current.finished_at = _now()
                current.duration_ms = int((time.monotonic() - started) * 1000)
    return get_job(user_id, job_id)


def load_chunk_set(user_id: int, chunk_set_id: str) -> ChunkSet:
    """Reload complete parent/child evidence and reject corrupted snapshots."""
    with session_scope() as db:
        row = db.get(StoredChunkSet, chunk_set_id)
        if row is None:
            raise LookupError("ChunkSet not found")
        _owned_document(db, user_id, row.document_id)
        chunks = ChunkSet.model_validate_json(row.payload_json)
        if chunks.chunk_set_id != row.id or chunks.document_id != row.document_id or not chunks.verify():
            raise ValueError("Stored ChunkSet integrity check failed")
        return chunks
