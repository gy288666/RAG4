import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.index_rebuild import IndexRebuild
from app.models.usage_log import UsageLog
from app.services import config_service, index_rebuild_service as rebuilds, index_version_service as versions
from test_chunking_integration import upload

BASE = "/api/v1/index-rebuilds"


@pytest.fixture
def corpus(client, user_headers, monkeypatch):
    doc_id, user_id, _ = upload(client, user_headers)
    config = SimpleNamespace(embedding_provider="remote", embedding_base_url="https://configured.invalid/v1",
                             embedding_model="configured-model", embedding_version="configured-v1")
    monkeypatch.setattr(config_service, "load_runtime_config", lambda db: config)
    return doc_id, user_id, config


def create(client, headers):
    result = client.post(BASE, headers=headers, json={"dimension": 3})
    assert result.status_code == 200, result.text
    return result.json()["data"]


@pytest.mark.parametrize("method,path", [("get", ""), ("post", ""), ("get", "/missing"), ("post", "/missing/cancel")])
def test_requires_auth(client, method, path):
    assert getattr(client, method)(BASE + path).status_code == 401


def test_create_progress_cancel_and_audit(client, user_headers, corpus):
    _, user_id, _ = corpus
    before = versions.active_state(user_id)
    task = create(client, user_headers)
    assert task["status"] == "pending" and task["attempt"] == 0
    assert task["document_count"] == 1 and task["completed_document_count"] == 0
    assert task["embedding_model"] == "configured-model"
    stored = rebuilds.get_rebuild(user_id, task["id"])
    assert json.loads(stored.request_json)["embedding"]["endpoint"] == "https://configured.invalid/v1/embeddings"
    assert "request_json" not in task and "endpoint" not in task and "user_id" not in task
    assert client.get(BASE + "/" + task["id"], headers=user_headers).json()["data"] == task
    for _ in range(2):
        result = client.post(BASE + "/" + task["id"] + "/cancel", headers=user_headers)
        assert result.json()["data"]["status"] == "cancelled"
    assert versions.active_state(user_id) == before
    with SessionLocal() as db:
        logs = list(db.scalars(select(UsageLog).where(UsageLog.event_type.in_(
            ["index_rebuild_create", "index_rebuild_cancel"]))))
        assert len(logs) == 3 and all(log.is_success and log.duration_ms >= 0 for log in logs)


def test_cross_user_and_admin_cannot_read_or_cancel(client, user_headers, admin_headers, corpus):
    task = create(client, user_headers)
    for suffix, method in [("", "get"), ("/cancel", "post")]:
        wrong = getattr(client, method)(BASE + "/" + task["id"] + suffix, headers=admin_headers)
        missing = getattr(client, method)(BASE + "/missing" + suffix, headers=admin_headers)
        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json()
    assert client.get(BASE, headers=admin_headers).json()["data"]["total"] == 0
    assert rebuilds.get_rebuild(corpus[1], task["id"]).status == "pending"


def test_owner_pagination(client, user_headers, corpus):
    ids = [create(client, user_headers)["id"] for _ in range(3)]
    rows = [client.get(BASE, headers=user_headers, params={"offset": i, "limit": 1}).json()["data"] for i in range(3)]
    assert all(row["total"] == 3 for row in rows)
    assert {row["items"][0]["id"] for row in rows} == set(ids)
    assert client.get(BASE, headers=user_headers, params={"limit": 101}).status_code == 400
    assert client.get(BASE, headers=user_headers, params={"offset": -1}).status_code == 400


@pytest.mark.parametrize("body", [{"dimension": 0}, {"dimension": True}, {"dimension": 3, "api_key": "secret"},
                                    {"dimension": 3, "endpoint": "http://localhost"}, {"dimension": 3, "user_id": 999}])
def test_invalid_or_privileged_inputs_rejected(client, user_headers, corpus, body):
    assert client.post(BASE, headers=user_headers, json=body).status_code == 400
    assert rebuilds.list_rebuilds(corpus[1])[1] == 0


def test_non_remote_configuration_rejected(client, user_headers, corpus):
    corpus[2].embedding_provider = "local"
    assert client.post(BASE, headers=user_headers, json={"dimension": 3}).status_code == 400


def test_empty_corpus_does_not_create_task(client, user_headers):
    assert client.post(BASE, headers=user_headers, json={"dimension": 3}).status_code == 400


def test_running_cancel_is_cooperative(client, user_headers, corpus):
    task = create(client, user_headers)
    with SessionLocal() as db:
        row = db.get(IndexRebuild, task["id"])
        row.status = "running"
        db.commit()
    result = client.post(BASE + "/" + task["id"] + "/cancel", headers=user_headers).json()["data"]
    assert result["status"] == "running" and result["cancel_requested"] is True


def test_snapshot_not_rewritten_by_later_config_change(client, user_headers, corpus):
    task = create(client, user_headers)
    corpus[2].embedding_version = "later-version"
    detail = client.get(BASE + "/" + task["id"], headers=user_headers).json()["data"]
    assert detail["embedding_version"] == "configured-v1"


def test_missing_source_error_does_not_disclose_local_path(client, user_headers, corpus, tmp_path):
    from app.models.document import Document
    private_path = str(tmp_path / "private-missing-file")
    with SessionLocal() as db:
        db.get(Document, corpus[0]).local_path = private_path
        db.commit()
    result = client.post(BASE, headers=user_headers, json={"dimension": 3})
    assert result.status_code == 400 and "private-missing-file" not in result.text
    assert rebuilds.list_rebuilds(corpus[1])[1] == 0
