"""Versioned index -> owned corpus -> research tools using both vector adapters."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.user import User
from app.research.model import CompletionSpec
from app.research import runtime
from app.research.store import SQLResearchTaskStore
from app.services import index_build_service as builds, index_job_service as jobs, index_version_service as versions
from test_chunking_integration import storage, upload
from test_research_agent import FakeModel, finish


class Embedding:
    def __init__(self, **kwargs):
        pass
    def embed_documents(self, texts):
        return [[1., 2., 3.] for _ in texts]
    def embed_query(self, text):
        return [1., 2., 3.]


@pytest.fixture
def published(client, user_headers, storage, monkeypatch):
    monkeypatch.setattr(builds, "RemoteEmbeddingAdapter", Embedding)
    monkeypatch.setattr(runtime, "RemoteEmbeddingAdapter", Embedding)
    monkeypatch.setattr(runtime, "JsonResearchModel", lambda *args, **kwargs: FakeModel())
    config = SimpleNamespace(embedding_base_url="https://model.example/v1", embedding_api_key="private",
        llm_base_url="https://model.example/v1", llm_model="fake", llm_api_key="private")
    ids, docs = [], []
    spec = builds.EmbeddingSpec(endpoint="https://model.example/v1/embeddings", model_id="frozen", version="v1", dimension=3)
    for i, text in enumerate(("DPR uses BERT.", "FiD uses T5.", "REALM uses BERT.")):
        document_id, owner, _ = upload(client, user_headers, name=f"paper{i}.txt", text=text)
        prepared = jobs.run_job(owner, jobs.create_job(owner, document_id, idempotency_key=f"prepare-{i}").id)
        build = builds.create_build(owner, prepared.chunk_set_id, spec, idempotency_key=f"build-{i}")
        assert builds.run_build(owner, build.id, api_key="unused", store=storage).status == "validated"
        ids.append(build.id)
        docs.append(document_id)
    version = versions.create_version(owner, ids, store=storage)
    monkeypatch.setattr(runtime.config_service, "load_runtime_config", lambda db: config)
    completion = CompletionSpec(endpoint="https://model.example/v1/chat/completions", model_id="fake")
    task = runtime.create_task(owner, version.id, docs, "比较方法、数据集、结果和局限", completion=completion, vector_store=storage)
    return owner, task, version, config


def test_retained_snapshot_completes_without_activation_or_baseline_changes(published, storage):
    owner, task, version, _ = published
    baseline = storage.read_records(owner, index_version="baseline")
    assert versions.active_state(owner) == (None, 0)
    done = finish(runtime.configured_agent(vector_store=storage), task)
    assert done.status == "completed" and len(done.artifact.rows) == 3
    assert versions.active_state(owner) == (None, 0)
    assert storage.read_records(owner, index_version="baseline") == baseline
    # Changing the active pointer is independent of this explicit retained ID.
    versions.switch_version(owner, version.id, expected_revision=0, store=storage)
    assert SQLResearchTaskStore().load(owner, task.id).index_version_id == version.id


def test_changed_source_fails_closed_preserving_index_and_task_history(published, storage):
    owner, task, version, _ = published
    with SessionLocal() as db:
        path = db.get(Document, task.sources[0].document_id).local_path
    Path(path).write_text("Changed source bytes", encoding="utf-8")
    failed = runtime.configured_agent(vector_store=storage).step(owner, task.id)
    assert failed.status == "failed" and failed.error_code == "research_context_unavailable"
    assert failed.bundles == () and failed.artifact is None
    assert versions.describe_version(owner, version.id)["manifest_integrity"] == "valid"
    assert versions.active_state(owner) == (None, 0)


def test_wrong_credentials_endpoint_or_disabled_owner_cannot_execute(published, storage):
    owner, task, _, config = published
    config.llm_base_url = "https://other.example/v1"
    failed = runtime.configured_agent(vector_store=storage).step(owner, task.id)
    assert failed.error_code == "research_context_unavailable"
    agent = runtime.configured_agent(vector_store=storage)
    agent.control(owner, task.id, "resume", failed.revision)
    config.llm_base_url = "https://model.example/v1"
    with SessionLocal() as db:
        db.get(User, owner).status = 0
        db.commit()
    disabled = agent.step(owner, task.id)
    assert disabled.status == "failed" and not disabled.claims


@pytest.mark.parametrize("protocol", ["numeric-model-v2", "source-handles-v4"])
def test_create_api_and_step_use_frozen_owned_version(client, user_headers, published, storage, protocol):
    owner, task, version, _ = published
    body = {"index_version_id": version.id, "document_ids": [s.document_id for s in task.sources], "goal": "比较文献"}
    if protocol != "numeric-model-v2":
        body["verification_protocol"] = protocol
    created = client.post("/api/v1/research-tasks", headers=user_headers, json=body)
    assert created.status_code == 200, created.json()
    assert created.json()["data"]["completion"]["verification_protocol"] == protocol
    task_id = created.json()["data"]["id"]
    step = client.post(f"/api/v1/research-tasks/{task_id}/run", headers=user_headers)
    assert step.status_code == 200 and step.json()["data"]["steps"][0]["status"] == "succeeded"
    assert client.get("/api/v1/research-tasks", headers=user_headers).json()["data"]["total"] == 2
    assert versions.active_state(owner) == (None, 0)
