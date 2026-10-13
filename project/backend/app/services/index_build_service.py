"""Build and validate isolated candidate vectors; never activate them.

Credentials are supplied at execution and never persisted. A failed attempt
keeps its namespace for diagnosis; retries must create a new build/key.
"""

import hashlib
import json
import math
import time
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import session_scope
from app.modeling.adapters import RemoteEmbeddingAdapter
from app.models.document import Document
from app.models.index_build import IndexBuild
from app.services.index_job_service import _now, _owned_document, load_chunk_set
from app.services.vector_store import BaseVectorStore, VectorRecord, get_vector_store, records_digest
from app.utils.ids import generate_id


class EmbeddingSpec(BaseModel):
    """Non-secret model contract frozen before execution.

    This slice supports remote models. The version is an operator-assigned
    revision; providers that mutate weights behind a model ID cannot be pinned.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: Literal["remote"] = "remote"
    endpoint: str = Field(min_length=1, max_length=512)
    model_id: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=128)
    dimension: int = Field(gt=0, le=65536)
    timeout_seconds: float = Field(default=30, gt=0, le=300)

    @field_validator("endpoint")
    @classmethod
    def public_endpoint(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme not in {"https", "http"} or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise ValueError("Endpoint must not contain credentials, query or fragment")
        return value


def get_build(user_id: int, build_id: str) -> IndexBuild:
    with session_scope() as db:
        row = db.get(IndexBuild, build_id)
        if row is None or row.user_id != user_id:
            raise LookupError("Build not found")
        _owned_document(db, user_id, row.document_id)
        db.expunge(row)
        return row


def create_build(user_id: int, chunk_set_id: str, spec: EmbeddingSpec, *, idempotency_key: str) -> IndexBuild:
    """Allocate a private namespace; same key/request reuses the attempt."""
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 64 or idempotency_key != idempotency_key.strip():
        raise ValueError("Invalid idempotency key")
    chunks = load_chunk_set(user_id, chunk_set_id)
    if not chunks.child_chunks:
        raise ValueError("Empty ChunkSet")
    spec_json = spec.model_dump_json()

    def existing(db):
        row = db.scalar(select(IndexBuild).where(IndexBuild.user_id == user_id,
                        IndexBuild.idempotency_key == idempotency_key))
        if row and (row.chunk_set_id != chunk_set_id or row.embedding_spec_json != spec_json):
            raise ValueError("Idempotency key conflicts with another build")
        return row

    try:
        with session_scope() as db:
            row = existing(db)
            if row is None:
                build_id = generate_id("build")
                row = IndexBuild(id=build_id, user_id=user_id, document_id=chunks.document_id,
                                 chunk_set_id=chunk_set_id, idempotency_key=idempotency_key,
                                 index_version="staging_" + build_id, embedding_spec_json=spec_json)
                db.add(row)
                db.flush()
            build_id = row.id
    except IntegrityError:
        with session_scope() as db:
            row = existing(db)
            if row is None:
                raise
            build_id = row.id
    return get_build(user_id, build_id)


def _valid_vector(vector, dimension: int) -> bool:
    return (len(vector) == dimension and all(isinstance(x, (float, int)) and not isinstance(x, bool)
            and math.isfinite(x) for x in vector) and any(x != 0 for x in vector))


def _verify_records(expected: list[VectorRecord], actual: list[VectorRecord], dimension: int) -> None:
    wanted = {r.id: r for r in expected}
    if len(actual) != len(expected) or {r.id for r in actual} != set(wanted):
        raise ValueError("Vector IDs/count mismatch")
    for record in actual:
        reference = wanted[record.id]
        if record.text != reference.text or record.metadata() != reference.metadata():
            raise ValueError("Vector provenance mismatch")
        if not _valid_vector(record.embedding, dimension) or not all(
            math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-7)
            for a, b in zip(record.embedding, reference.embedding, strict=True)
        ):
            raise ValueError("Vector value/dimension mismatch")


def run_build(user_id: int, build_id: str, *, api_key: str,
              store: BaseVectorStore | None = None) -> IndexBuild:
    """Claim once, embed, stage, read back and publish a validation manifest.

    No global runtime model setting is consulted, including DEV_MOCK_AI.
    Tests inject the adapter factory. Credentials are used only by that adapter.
    """
    build = get_build(user_id, build_id)
    with session_scope() as db:
        claimed = db.execute(update(IndexBuild).where(IndexBuild.id == build_id,
                             IndexBuild.status == "pending").values(status="running", started_at=_now())).rowcount
    if not claimed:
        return get_build(user_id, build_id)
    started = time.monotonic()
    stage = "load"
    try:
        spec = EmbeddingSpec.model_validate_json(build.embedding_spec_json)
        chunks = load_chunk_set(user_id, build.chunk_set_id)
        store = store if store is not None else get_vector_store()
        # Existing contents mean the namespace is not fresh; never overwrite it.
        if store.read_records(user_id, index_version=build.index_version):
            raise ValueError("Candidate namespace is not empty")
        stage = "embedding"
        adapter = RemoteEmbeddingAdapter(endpoint=spec.endpoint, api_key=api_key,
                                         model_id=spec.model_id, version=spec.version,
                                         timeout=spec.timeout_seconds)
        vectors = adapter.embed_documents([c.text for c in chunks.child_chunks])
        if len(vectors) != len(chunks.child_chunks) or not all(_valid_vector(v, spec.dimension) for v in vectors):
            raise ValueError("Invalid embedding count, dimension or values")
        # Lock only the publish section, not the remote network request.
        with session_scope() as db:
            doc = db.scalar(select(Document).where(Document.id == build.document_id,
                            Document.user_id == user_id).with_for_update())
            if doc is None:
                raise LookupError("Document not found")
            records = [VectorRecord(
                id=c.chunk_id, text=c.text, embedding=v, doc_id=doc.id, user_id=user_id,
                file_name=doc.file_name, chunk_index=c.chunk_index, page=c.page_start,
                embedding_model_version=spec.version, chunking_version=chunks.chunking_version,
                chunk_set_id=chunks.chunk_set_id,
                chunk_metadata_json=json.dumps(c.model_dump(mode="json", exclude={"text"}),
                                               ensure_ascii=False, sort_keys=True),
            ) for c, v in zip(chunks.child_chunks, vectors, strict=True)]
            stage = "write"
            store.add(user_id, records, index_version=build.index_version)
            stage = "verify"
            stored_records = store.read_records(user_id, index_version=build.index_version)
            _verify_records(records, stored_records, spec.dimension)
            manifest = {
                "schema_version": "index-validation-v1", "chunk_set_id": chunks.chunk_set_id,
                "input_id": chunks.input_id, "parser_version": chunks.parser_version,
                "chunking_version": chunks.chunking_version, "tokenizer_id": chunks.tokenizer_id,
                "engine_version": chunks.engine_version, "embedding": spec.model_dump(mode="json"),
                "index_version": build.index_version, "record_count": len(records),
                "dimension": spec.dimension,
                "records_sha256": records_digest(stored_records),
                "record_ids_sha256": hashlib.sha256(json.dumps(sorted(r.id for r in records)).encode()).hexdigest(),
            }
            stage = "publish"
            current = db.get(IndexBuild, build_id)
            current.status = "validated"
            current.manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            current.finished_at = _now()
            current.duration_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:
        with session_scope() as db:
            current = db.get(IndexBuild, build_id)
            if current is not None:
                current.status = "failed"
                current.error_stage = stage
                current.error_code = type(exc).__name__[:64]
                current.finished_at = _now()
                current.duration_ms = int((time.monotonic() - started) * 1000)
    return get_build(user_id, build_id)
