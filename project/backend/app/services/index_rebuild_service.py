"""Explicit batch rebuild, checkpointed retry and cooperative cancellation.

Never mutates active pointers. A ready result is activated separately using its
base_revision. Explicit interrupted-task recovery creates a fenced successor;
there is no automatic liveness detection or lease-based takeover.
"""
import json
import hashlib
import re
import time

from sqlalchemy import case, func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.chunking import ChunkingConfig
from app.core.config import settings
from app.core.database import session_scope
from app.models.document import Document
from app.models.index_rebuild import IndexRebuild
from app.models.rebuild_recovery import RebuildRecovery
from app.models.rebuild_request import RebuildRequest
from app.services import index_job_service as jobs, index_build_service as builds
from app.services import index_version_service as versions
from app.services import usage_service
from app.services.vector_store import get_vector_store
from app.utils.ids import generate_id


def _sources(user_id):
    with session_scope() as db:
        docs = db.scalars(select(Document).where(Document.user_id == user_id).order_by(Document.id)).all()
        if not docs or any(d.status != "ready" for d in docs):
            raise ValueError("All documents must be ready")
        return [{"id": d.id, "name": d.file_name, "sha256": jobs._digest(d.local_path)} for d in docs]


def get_rebuild(user_id: int, task_id: str) -> IndexRebuild:
    with session_scope() as db:
        task = db.get(IndexRebuild, task_id)
        if task is None or task.user_id != user_id:
            raise LookupError("Rebuild not found")
        db.expunge(task)
        return task


def list_rebuilds(user_id: int, *, limit: int = 20, offset: int = 0) -> tuple[list[IndexRebuild], int]:
    """Bounded owner-scoped page; newest first with deterministic ID tie-break."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    with session_scope() as db:
        owned = IndexRebuild.user_id == user_id
        total = db.scalar(select(func.count()).select_from(IndexRebuild).where(owned))
        tasks = list(db.scalars(select(IndexRebuild).where(owned).order_by(
            IndexRebuild.created_at.desc(), IndexRebuild.id.desc()).offset(offset).limit(limit)))
        for task in tasks:
            db.expunge(task)
        return tasks, total


class RebuildRequestConflict(ValueError):
    """A creation key is already bound to different model/chunking parameters."""


class RebuildQuotaExceeded(ValueError):
    """Admission rejected without creating a task or an idempotency mapping."""

    def __init__(self, limit: int, open_count: int):
        self.limit = limit
        self.open_count = open_count
        super().__init__("Open rebuild task quota exceeded")


def _lock_rebuild_owner(db, user_id):
    """Serialize admission/recovery across processes, including SQLite.

    A no-op UPDATE locks the existing user row on InnoDB and acquires SQLite's
    write lock before any snapshot SELECT. Raw SQL deliberately avoids the ORM
    User.updated_at onupdate expression. Locks end with this transaction; file
    hashing and model calls must stay outside it. No new counter can drift.
    """
    result = db.execute(text("UPDATE users SET id = id WHERE id = :user_id"), {"user_id": user_id})
    if result.rowcount != 1:
        raise ValueError("Rebuild owner not found")


def _request_in_session(db, user_id, key, fingerprint):
    row = db.get(RebuildRequest, (user_id, key))
    if row is None:
        return None
    if row.request_sha256 != fingerprint:
        raise RebuildRequestConflict("Creation key already used with different parameters")
    task = db.get(IndexRebuild, row.task_id)
    if task is None or task.user_id != user_id:
        raise LookupError("Rebuild not found")
    db.expunge(task)
    return task


def _existing_request(user_id, key, fingerprint):
    with session_scope() as db:
        return _request_in_session(db, user_id, key, fingerprint)


def create_rebuild(user_id: int, spec: builds.EmbeddingSpec,
                   config: ChunkingConfig | None = None, *, idempotency_key: str | None = None) -> IndexRebuild:
    """Create a frozen corpus task, or replay an existing user-scoped request.

    With a key, model/chunking parameters determine request compatibility; corpus
    and active revision are frozen only on first creation. Replays never rescan
    files or restart completed/cancelled work. No key retains legacy behavior.
    New tasks are admitted only below the configured owner quota. Pending,
    running and failed tasks consume capacity; ready/cancelled history does not.
    """
    config = config or ChunkingConfig()
    fingerprint = hashlib.sha256(json.dumps({"embedding": spec.model_dump(), "chunking": config.model_dump()},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", idempotency_key):
            raise ValueError("Invalid creation key")
        existing = _existing_request(user_id, idempotency_key, fingerprint)
        if existing is not None:
            return existing
    _, revision = versions.active_state(user_id)
    payload = {"documents": _sources(user_id), "embedding": spec.model_dump(),
               "chunking": config.model_dump()}
    try:
        with session_scope() as db:
            _lock_rebuild_owner(db, user_id)
            # Another request may have won while sources were being hashed.
            # Replay must precede quota enforcement, even when capacity is full.
            if idempotency_key is not None:
                existing = _request_in_session(db, user_id, idempotency_key, fingerprint)
                if existing is not None:
                    return existing
            open_count = db.scalar(select(func.count()).select_from(IndexRebuild).where(
                IndexRebuild.user_id == user_id,
                IndexRebuild.status.in_(["pending", "running", "failed"])))
            limit = settings.RAG4_MAX_OPEN_REBUILDS_PER_USER
            if open_count >= limit:
                raise RebuildQuotaExceeded(limit, open_count)
            task = IndexRebuild(id=generate_id("rebuild"), user_id=user_id, base_revision=revision,
                                request_json=json.dumps(payload, sort_keys=True))
            db.add(task)
            db.flush()
            task_id = task.id
            if idempotency_key is not None:
                db.add(RebuildRequest(user_id=user_id, request_key=idempotency_key,
                                      request_sha256=fingerprint, task_id=task_id))
    except IntegrityError:
        # Loser task rolls back with its request row. New transaction observes winner.
        if idempotency_key is not None:
            existing = _existing_request(user_id, idempotency_key, fingerprint)
            if existing is not None:
                return existing
        raise
    return get_rebuild(user_id, task_id)


def cancel_rebuild(user_id: int, task_id: str) -> IndexRebuild:
    """Pending/failed tasks cancel immediately; running tasks stop at boundaries."""
    get_rebuild(user_id, task_id)
    with session_scope() as db:
        db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id,
            IndexRebuild.status.in_(["pending", "failed"])).values(
                cancel_requested=True, status="cancelled", finished_at=jobs._now()))
        db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id,
            IndexRebuild.status == "running").values(cancel_requested=True))
    return get_rebuild(user_id, task_id)


def recover_rebuild(user_id: int, task_id: str) -> IndexRebuild:
    """Recover explicitly; record operation duration and success/failure."""
    with usage_service.track("index_recovery", user_id=user_id, ref_id=task_id):
        return _recover_rebuild(user_id, task_id)


def _recover_rebuild(user_id: int, task_id: str) -> IndexRebuild:
    """Fence a running task and atomically create its single successor.

    Safe even if the original process is still executing: its cancellation flag
    is permanent, and subsequent side effects target its own task/namespaces.
    Copy only already committed checkpoints. Repeated/concurrent recovery returns
    the same successor. Pending, failed, ready and user-cancelled tasks reject
    recovery (failed tasks use run_rebuild). Never refresh base_revision silently.
    """
    get_rebuild(user_id, task_id)  # Ownership check before any mutation.
    with session_scope() as db:
        # Recovery swaps one open task for one successor, including when a
        # lowered limit is already exceeded. Use the same admission lock order.
        _lock_rebuild_owner(db, user_id)
        fenced = db.execute(update(IndexRebuild).where(
            IndexRebuild.id == task_id, IndexRebuild.user_id == user_id,
            IndexRebuild.status == "running", IndexRebuild.cancel_requested.is_(False),
        ).values(status="cancelled", cancel_requested=True, finished_at=jobs._now())).rowcount
        if fenced:
            source = db.get(IndexRebuild, task_id)
            successor = IndexRebuild(
                id=generate_id("rebuild"), user_id=user_id, base_revision=source.base_revision,
                request_json=source.request_json, checkpoints_json=source.checkpoints_json)
            db.add(successor)
            db.flush()
            db.add(RebuildRecovery(source_task_id=task_id, target_task_id=successor.id, user_id=user_id))
    # New transaction observes the winning recovery, including on MySQL RR.
    with session_scope() as db:
        recovery = db.get(RebuildRecovery, task_id)
        if recovery is None or recovery.user_id != user_id:
            raise ValueError("Only uncancelled running tasks can be recovered")
        target_id = recovery.target_task_id
    return get_rebuild(user_id, target_id)


def run_rebuild(user_id: int, task_id: str, *, api_key: str, store=None) -> IndexRebuild:
    """Run or retry a failed task; completed documents never re-embed on retry.

    Failure retains both checkpoints and earlier attempt records. A new attempt
    gets fresh per-document jobs/namespaces. Cancellation never activates output.
    """
    get_rebuild(user_id, task_id)
    with session_scope() as db:
        claimed = db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id,
            IndexRebuild.status.in_(["pending", "failed"]), IndexRebuild.cancel_requested.is_(False)
        ).values(status="running", attempt=IndexRebuild.attempt + 1, error_code=None,
                 error_document_id=None, finished_at=None)).rowcount
    if not claimed:
        return get_rebuild(user_id, task_id)
    task = get_rebuild(user_id, task_id)
    started = time.monotonic()
    document_id = None
    try:
        request = json.loads(task.request_json)
        if _sources(user_id) != request["documents"]:
            raise ValueError("Corpus changed")
        store = store if store is not None else get_vector_store()
        checkpoints = json.loads(task.checkpoints_json)
        spec = builds.EmbeddingSpec.model_validate(request["embedding"])
        config = ChunkingConfig.model_validate(request["chunking"])
        for i, source in enumerate(request["documents"]):
            document_id = source["id"]
            if get_rebuild(user_id, task_id).cancel_requested:
                break
            if document_id in checkpoints:
                versions._validate_member(user_id, checkpoints[document_id], store)
                continue
            key = f"{task_id}-{task.attempt}-{i}"
            prepared = jobs.create_job(user_id, document_id, idempotency_key=key, config=config)
            if prepared.source_sha256 != source["sha256"]:
                raise ValueError("Source changed")
            prepared = jobs.run_job(user_id, prepared.id)
            if prepared.status != "succeeded":
                raise RuntimeError("Preparation failed")
            if get_rebuild(user_id, task_id).cancel_requested:
                break
            build = builds.create_build(user_id, prepared.chunk_set_id, spec, idempotency_key=key)
            build = builds.run_build(user_id, build.id, api_key=api_key, store=store)
            if build.status != "validated":
                raise RuntimeError("Candidate build failed")
            checkpoints[document_id] = build.id
            with session_scope() as db:
                db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id).values(
                    checkpoints_json=json.dumps(checkpoints, sort_keys=True)))
        document_id = None
        cancelled = get_rebuild(user_id, task_id).cancel_requested
        version = None
        if not cancelled:
            if _sources(user_id) != request["documents"]:
                raise ValueError("Corpus changed")
            version = versions.create_version(user_id, list(checkpoints.values()), store=store)
        with session_scope() as db:
            # Evaluate cancellation in the UPDATE itself, including on SQLite.
            db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id).values(
                status=case((IndexRebuild.cancel_requested.is_(True), "cancelled"), else_="ready"),
                version_id=case((IndexRebuild.cancel_requested.is_(True), None), else_=version.id if version else None),
                finished_at=jobs._now(),
                duration_ms=IndexRebuild.duration_ms + int((time.monotonic() - started) * 1000)))
    except Exception as exc:
        with session_scope() as db:
            db.execute(update(IndexRebuild).where(IndexRebuild.id == task_id).values(
                status=case((IndexRebuild.cancel_requested.is_(True), "cancelled"), else_="failed"),
                error_code=type(exc).__name__[:64], error_document_id=document_id,
                finished_at=jobs._now(),
                duration_ms=IndexRebuild.duration_ms + int((time.monotonic() - started) * 1000)))
    return get_rebuild(user_id, task_id)
