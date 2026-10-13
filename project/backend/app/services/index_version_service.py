"""Complete user index manifests, guarded activation/rollback and snapshot search.

No pointer means the original RAG3/RAG4 upload retrieval route. An active snapshot
must cover every current document. Changed/deleted documents fail closed until
explicit deactivation or a new complete version is activated.
"""
import hashlib
import json

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import session_scope
from app.modeling.adapters import RemoteEmbeddingAdapter
from app.models.document import Document
from app.models.index_build import IndexBuild
from app.models.index_version import ActiveIndex, IndexVersion, IndexSwitch
from app.models.user import User
from app.services import usage_service
from app.services.embedding_service import EmbeddingError, build_endpoint
from app.services.index_build_service import EmbeddingSpec, _valid_vector
from app.services.index_job_service import load_chunk_set
from app.services.vector_store import get_vector_store, records_digest
from app.utils.ids import generate_id
from app.utils.datetime_utils import fmt


def _read_manifest(row):
    """Validate stored shape before any use; all corruption becomes ValueError.

    This validates persisted identity only. Current document and vector validation
    remains mandatory at activation/search, not historical browsing.
    """
    try:
        if _hash(row.manifest_json) != row.manifest_sha256:
            raise ValueError("digest")
        data = json.loads(row.manifest_json)
        if (not isinstance(data, dict) or data.get("schema") != "user-index-v1"
                or type(data.get("user_id")) is not int or data["user_id"] != row.user_id):
            raise ValueError("identity")
        EmbeddingSpec.model_validate(data["embedding"])
        documents, members = data["documents"], data["members"]
        if (not isinstance(documents, dict) or not documents
                or not all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in documents.items())
                or not isinstance(members, list) or len(members) != len(documents)):
            raise ValueError("coverage")
        for member in members:
            if not isinstance(member, dict) or not all(isinstance(member.get(k), str) and member[k]
                for k in ("build_id", "document_id", "chunk_set_id", "namespace", "records_sha256")):
                raise ValueError("member")
            digest = member["records_sha256"]
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("member digest")
        if ({m["document_id"] for m in members} != set(documents)
                or len({m["build_id"] for m in members}) != len(members)
                or len({m["namespace"] for m in members}) != len(members)):
            raise ValueError("duplicate or incomplete members")
        return data
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("Version manifest integrity check failed") from error


def _describe_version(row, active_id, *, detail=False):
    """Metadata only: historical visibility does not imply current activatability."""
    result = {"id": row.id, "created_at": fmt(row.created_at), "is_active": row.id == active_id,
              "manifest_integrity": "invalid", "document_count": None, "embedding": None}
    try:
        data = _read_manifest(row)
        spec = EmbeddingSpec.model_validate(data["embedding"])
        documents, members = data["documents"], data["members"]
        fields = ("build_id", "document_id", "chunk_set_id")
        safe_members = [{key: member[key] for key in fields} for member in members]
        result.update(manifest_integrity="valid", document_count=len(documents),
                      embedding={"model_id": spec.model_id, "version": spec.version, "dimension": spec.dimension})
        if detail:
            result["documents"] = [{"id": key, "file_name": value} for key, value in sorted(documents.items())]
            result["members"] = safe_members
    except (ValueError, TypeError, KeyError):
        pass
    return result


def list_versions(user_id: int, *, limit=20, offset=0):
    """Bounded SQL owner filter, newest first. Never reads vectors or writes data."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    with session_scope() as db:
        owned = IndexVersion.user_id == user_id
        pointer = db.get(ActiveIndex, user_id)
        active_id = pointer.version_id if pointer else None
        total = db.scalar(select(func.count()).select_from(IndexVersion).where(owned))
        rows = db.scalars(select(IndexVersion).where(owned).order_by(
            IndexVersion.created_at.desc(), IndexVersion.id.desc()).offset(offset).limit(limit)).all()
        return {"items": [_describe_version(row, active_id) for row in rows], "total": total,
                "limit": limit, "offset": offset}


def describe_version(user_id: int, version_id: str):
    with session_scope() as db:
        row = db.get(IndexVersion, version_id)
        if row is None or row.user_id != user_id:
            raise LookupError("Index version not found")
        pointer = db.get(ActiveIndex, user_id)
        return _describe_version(row, pointer.version_id if pointer else None, detail=True)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _documents(db, user_id):
    docs = db.scalars(select(Document).where(Document.user_id == user_id)).all()
    if not docs or any(d.status != "ready" for d in docs):
        raise ValueError("All documents must be ready before version use")
    return {d.id: d.file_name for d in docs}


def _validate_member(user_id, build_id, store):
    with session_scope() as db:
        build = db.get(IndexBuild, build_id)
        if build is None or build.user_id != user_id or build.status != "validated":
            raise ValueError("Build must be validated and owned by user")
        spec = EmbeddingSpec.model_validate_json(build.embedding_spec_json)
        build_manifest = json.loads(build.manifest_json)
        namespace, chunk_set_id, doc_id = build.index_version, build.chunk_set_id, build.document_id
        if (build_manifest.get("embedding") != spec.model_dump()
                or build_manifest.get("index_version") != namespace
                or build_manifest.get("chunk_set_id") != chunk_set_id):
            raise ValueError("Build manifest configuration changed")
    chunks = load_chunk_set(user_id, chunk_set_id)
    records = store.read_records(user_id, index_version=namespace)
    if build_manifest.get("record_count") != len(records):
        raise ValueError("Build manifest count changed")
    wanted = {c.chunk_id: c for c in chunks.child_chunks}
    if len(records) != len(wanted) or {r.id for r in records} != set(wanted):
        raise ValueError("Candidate coverage changed")
    for record in records:
        chunk = wanted[record.id]
        if (record.user_id != user_id or record.doc_id != doc_id or record.chunk_set_id != chunk_set_id
                or record.text != chunk.text or record.chunk_index != chunk.chunk_index
                or record.page != chunk.page_start or record.chunking_version != chunks.chunking_version
                or record.embedding_model_version != spec.version
                or json.loads(record.chunk_metadata_json) != chunk.model_dump(mode="json", exclude={"text"})
                or not _valid_vector(record.embedding, spec.dimension)):
            raise ValueError("Candidate provenance changed")
    digest = records_digest(records)
    if build_manifest.get("records_sha256") != digest:
        raise ValueError("Candidate values changed or build needs revalidation")
    return {"build_id": build_id, "document_id": doc_id, "chunk_set_id": chunk_set_id,
            "namespace": namespace, "records_sha256": digest}, spec


def create_version(user_id: int, build_ids: list[str], *, store=None) -> IndexVersion:
    """Seal one validated build per document; reject partial/mixed-model sets."""
    store = store if store is not None else get_vector_store()
    if not build_ids or len(build_ids) != len(set(build_ids)):
        raise ValueError("Provide unique builds covering all documents")
    members, spec = [], None
    for build_id in sorted(build_ids):
        member, candidate_spec = _validate_member(user_id, build_id, store)
        if spec is not None and candidate_spec != spec:
            raise ValueError("All builds must use identical embedding configuration")
        spec = candidate_spec
        members.append(member)
    with session_scope() as db:
        docs = _documents(db, user_id)
        if len(members) != len(docs) or {m["document_id"] for m in members} != set(docs):
            raise ValueError("Version must cover every current document exactly once")
        payload = _json({"schema": "user-index-v1", "user_id": user_id,
                         "documents": docs, "embedding": spec.model_dump(), "members": members})
        row = IndexVersion(id=generate_id("version"), user_id=user_id,
                           manifest_json=payload, manifest_sha256=_hash(payload))
        db.add(row)
        db.flush()
        db.expunge(row)
        return row


def _manifest(db, user_id, version_id):
    version = db.get(IndexVersion, version_id)
    if version is None or version.user_id != user_id:
        raise LookupError("Index version not found")
    manifest = _read_manifest(version)
    if manifest["documents"] != _documents(db, user_id):
        raise ValueError("Documents changed; rebuild or deactivate the index")
    return manifest


def _verify_manifest(user_id, manifest, store):
    for member in manifest["members"]:
        verified, spec = _validate_member(user_id, member["build_id"], store)
        if verified != member or spec.model_dump() != manifest["embedding"]:
            raise ValueError("Version member changed")


def active_state(user_id: int) -> tuple[str | None, int]:
    with session_scope() as db:
        if db.get(User, user_id) is None:
            raise LookupError("User not found")
        row = db.get(ActiveIndex, user_id)
        return (row.version_id, row.revision) if row else (None, 0)


class ActiveRevisionConflict(ValueError):
    """Caller must reload the active revision before making another decision."""


def switch_version(user_id: int, version_id: str | None, *, expected_revision: int, store=None) -> tuple[str | None, int]:
    """Activate, roll back to a retained version, or deactivate with None.

    Caller supplies the revision read from active_state. The SQL CAS and audit
    insert commit together. Failures preserve the previous pointer.
    """
    # Deactivation must remain possible even when the vector backend is unavailable.
    if version_id is not None:
        store = store if store is not None else get_vector_store()
    # First-use initialization has a database uniqueness arbiter.
    try:
        with session_scope() as db:
            if db.get(User, user_id) is None:
                raise LookupError("User not found")
            if db.get(ActiveIndex, user_id) is None:
                db.add(ActiveIndex(user_id=user_id, revision=0))
    except IntegrityError:
        pass
    with usage_service.track("index_switch", user_id=user_id, ref_id=version_id):
        with session_scope() as db:
            row = db.get(ActiveIndex, user_id)
            if row.revision != expected_revision:
                raise ActiveRevisionConflict("Active revision conflict; reload before switching")
            previous = row.version_id
            if version_id is not None:
                db.scalars(select(Document).where(Document.user_id == user_id).with_for_update()).all()
                manifest = _manifest(db, user_id, version_id)
                _verify_manifest(user_id, manifest, store)
            changed = db.execute(update(ActiveIndex).where(
                ActiveIndex.user_id == user_id, ActiveIndex.revision == expected_revision,
            ).values(version_id=version_id, revision=expected_revision + 1)).rowcount
            if not changed:
                raise ActiveRevisionConflict("Active revision conflict; reload before switching")
            db.add(IndexSwitch(id=generate_id("switch"), user_id=user_id,
                               previous_version=previous, next_version=version_id,
                               revision=expected_revision + 1))
    return version_id, expected_revision + 1


def search_active(user_id: int, query: str, config, *, store=None):
    """Return None for baseline, otherwise search one immutable version snapshot.

    Endpoint must match the current credential binding; never forward a key to
    an endpoint from a different stored configuration. Model ID/version are frozen.
    """
    store = store if store is not None else get_vector_store()
    try:
        with session_scope() as db:
            pointer = db.get(ActiveIndex, user_id)
            version_id = pointer.version_id if pointer else None
        if version_id is None:
            return None
        with session_scope() as db:
            manifest = _manifest(db, user_id, version_id)
        _verify_manifest(user_id, manifest, store)
        spec = EmbeddingSpec.model_validate(manifest["embedding"])
        if spec.endpoint != build_endpoint(config.embedding_base_url, "embeddings"):
            raise ValueError("Active embedding endpoint does not match credential configuration")
        model = RemoteEmbeddingAdapter(endpoint=spec.endpoint, api_key=config.embedding_api_key,
            model_id=spec.model_id, version=spec.version, timeout=spec.timeout_seconds)
        vector = model.embed_query(query)
        if not _valid_vector(vector, spec.dimension):
            raise ValueError("Invalid query embedding")
        results = []
        for member in manifest["members"]:
            hits = store.search(user_id, vector, config.retrieval_top_n, index_version=member["namespace"])
            if any(h.doc_id != member["document_id"] for h in hits):
                raise ValueError("Unexpected document in active index")
            results.extend(hits)
        # Detect document deletion/upload while the external model was running.
        with session_scope() as db:
            _manifest(db, user_id, version_id)
        results.sort(key=lambda c: (-c.score, c.doc_id, c.chunk_index))
        return results[:config.retrieval_top_n]
    except Exception as exc:
        raise EmbeddingError("Active index is unavailable; rebuild or deactivate it") from exc
