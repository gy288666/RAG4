"""Complete coverage, guarded publication and retrieval/rollback contracts."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select

from app.core.database import SessionLocal
from app.models.index_version import IndexSwitch
from app.services import index_version_service as versions, index_build_service as builds
from app.services import index_job_service as jobs, rag_service, document_service, config_service
from app.services.embedding_service import EmbeddingError
from app.models.document import Document
from test_chunking_integration import storage, upload


@pytest.fixture
def complete(client, user_headers, storage, monkeypatch):
    class Model:
        def __init__(self, **kwargs):
            self.config = kwargs
        def embed_documents(self, texts):
            return [[1., 2., 3.] for _ in texts]
        def embed_query(self, text):
            return [1., 2., 3.]
    monkeypatch.setattr(builds, "RemoteEmbeddingAdapter", Model)
    monkeypatch.setattr(versions, "RemoteEmbeddingAdapter", Model)
    spec = builds.EmbeddingSpec(endpoint="https://model.example/v1/embeddings", model_id="fixed-model",
                                version="fixed-revision", dimension=3)
    ids, docs = [], []
    for i in range(2):
        doc, user, _ = upload(client, user_headers, name=f"paper{i}.txt", text=f"Evidence {i}. " * 30)
        prepared = jobs.run_job(user, jobs.create_job(user, doc, idempotency_key=f"prepare{i}").id)
        build = builds.create_build(user, prepared.chunk_set_id, spec, idempotency_key=f"build{i}")
        assert builds.run_build(user, build.id, api_key="secret", store=storage).status == "validated"
        ids.append(build.id)
        docs.append(doc)
    version = versions.create_version(user, ids, store=storage)
    config = SimpleNamespace(embedding_base_url="https://model.example/v1", embedding_api_key="secret", retrieval_top_n=10)
    return user, ids, docs, version, config


def test_activate_retrieve_and_rollback(complete, storage, monkeypatch):
    user, ids, docs, v1, config = complete
    baseline = storage.read_records(user, index_version="baseline")
    assert versions.search_active(user, "evidence", config, store=storage) is None
    assert versions.switch_version(user, v1.id, expected_revision=0, store=storage) == (v1.id, 1)
    hits = versions.search_active(user, "evidence", config, store=storage)
    assert {h.doc_id for h in hits} == set(docs)
    v2 = versions.create_version(user, ids, store=storage)
    versions.switch_version(user, v2.id, expected_revision=1, store=storage)
    versions.switch_version(user, v1.id, expected_revision=2, store=storage)
    assert versions.active_state(user) == (v1.id, 3)
    versions.switch_version(user, None, expected_revision=3, store=storage)
    assert versions.search_active(user, "evidence", config, store=storage) is None
    assert storage.read_records(user, index_version="baseline") == baseline
    with SessionLocal() as db:
        logs = db.scalars(select(IndexSwitch).order_by(IndexSwitch.revision)).all()
        assert [r.previous_version for r in logs] == [None, v1.id, v2.id, v1.id]


def test_partial_duplicate_and_cross_user_rejected(complete, storage):
    user, ids, _, version, _ = complete
    for selected in (ids[:1], [ids[0], ids[0]], []):
        with pytest.raises(ValueError):
            versions.create_version(user, selected, store=storage)
    with pytest.raises(ValueError):
        versions.create_version(user + 1, ids, store=storage)
    assert versions.active_state(user) == (None, 0)


def test_new_model_version_and_rollback_use_correct_namespaces(complete, storage):
    user, ids, _, v1, config = complete
    new_ids = []
    for i, build_id in enumerate(ids):
        old = builds.get_build(user, build_id)
        spec = builds.EmbeddingSpec.model_validate_json(old.embedding_spec_json).model_copy(update={"version": "revision-two"})
        new = builds.create_build(user, old.chunk_set_id, spec, idempotency_key=f"new{i}")
        assert builds.run_build(user, new.id, api_key="secret", store=storage).status == "validated"
        new_ids.append(new.id)
    with pytest.raises(ValueError, match="identical"):
        versions.create_version(user, [ids[0], new_ids[1]], store=storage)
    v2 = versions.create_version(user, new_ids, store=storage)
    versions.switch_version(user, v2.id, expected_revision=0, store=storage)
    assert {h.extra["embedding_model_version"] for h in versions.search_active(user, "query", config, store=storage)} == {"revision-two"}
    versions.switch_version(user, v1.id, expected_revision=1, store=storage)
    assert {h.extra["embedding_model_version"] for h in versions.search_active(user, "query", config, store=storage)} == {"fixed-revision"}


def test_concurrent_switch_has_one_winner(complete, storage):
    from concurrent.futures import ThreadPoolExecutor
    user, _, _, version, _ = complete
    versions.switch_version(user, version.id, expected_revision=0, store=storage)
    def attempt(_):
        try:
            return versions.switch_version(user, None, expected_revision=1, store=storage)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert results.count((None, 2)) == 1
    assert versions.active_state(user) == (None, 2)


def test_tampering_and_cas_preserve_pointer(complete, storage):
    user, ids, _, version, config = complete
    versions.switch_version(user, version.id, expected_revision=0, store=storage)
    with pytest.raises(ValueError, match="revision"):
        versions.switch_version(user, None, expected_revision=0, store=storage)
    member = json.loads(version.manifest_json)["members"][0]
    records = storage.read_records(user, index_version=member["namespace"])
    storage.add(user, [replace(records[0], embedding=[9., 8., 7.])], index_version=member["namespace"])
    with pytest.raises(ValueError, match="values"):
        versions.switch_version(user, version.id, expected_revision=1, store=storage)
    with pytest.raises(EmbeddingError):
        versions.search_active(user, "evidence", config, store=storage)
    assert versions.active_state(user) == (version.id, 1)
    versions.switch_version(user, None, expected_revision=1, store=storage)


def test_sql_switch_failure_rolls_back_pointer_and_audit(complete, storage):
    user, _, _, version, _ = complete
    def fail(*args):
        raise RuntimeError("audit insert failure")
    event.listen(IndexSwitch, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            versions.switch_version(user, version.id, expected_revision=0, store=storage)
    finally:
        event.remove(IndexSwitch, "before_insert", fail)
    assert versions.active_state(user) == (None, 0)
    with SessionLocal() as db:
        assert db.scalar(select(IndexSwitch)) is None


def test_live_retrieval_uses_frozen_model_and_existing_citations(complete, storage, monkeypatch):
    user, _, docs, version, _ = complete
    versions.switch_version(user, version.id, expected_revision=0, store=storage)
    with SessionLocal() as db:
        config = config_service.load_runtime_config(db)
    config.embedding_base_url = "https://model.example/v1"
    config.embedding_model = "unrelated-global-model"
    seen = []
    original = versions.RemoteEmbeddingAdapter
    def model(**kwargs):
        seen.append(kwargs["model_id"])
        return original(**kwargs)
    monkeypatch.setattr(versions, "RemoteEmbeddingAdapter", model)
    chunks, _ = rag_service.retrieve("Evidence", user, config)
    assert seen == ["fixed-model"]
    assert {c["doc_id"] for c in rag_service.build_citations(chunks)} == set(docs)


@pytest.mark.parametrize("change", ["upload", "delete", "endpoint"])
def test_changes_fail_closed_until_explicit_deactivation(complete, storage, client, user_headers, change):
    user, _, docs, version, config = complete
    versions.switch_version(user, version.id, expected_revision=0, store=storage)
    if change == "upload":
        upload(client, user_headers, name="new.txt", text="New evidence.")
    elif change == "delete":
        with SessionLocal() as db:
            document_service.delete_document(db, db.get(Document, docs[0]))
    else:
        config.embedding_base_url = "https://another.example/v1"
    with pytest.raises(EmbeddingError):
        versions.search_active(user, "Evidence", config, store=storage)
    versions.switch_version(user, None, expected_revision=1, store=storage)
    assert versions.search_active(user, "Evidence", config, store=storage) is None
