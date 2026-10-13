import pytest

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.index_version import IndexVersion
from app.services import index_version_service as versions
from app.services.rebuild_execution import execute_configured_rebuild
from test_chunking_integration import storage
from test_index_versions import complete
from test_rebuild_api import corpus, create
from test_rebuild_execution import ready_task

BASE = "/api/v1/index-versions"


@pytest.mark.parametrize("path", ["", "/missing"])
def test_history_requires_auth(client, path):
    assert client.get(BASE + path).status_code == 401


def test_history_pagination_and_safe_details(client, user_headers, complete, storage):
    user, builds, docs, first, _ = complete
    second = versions.create_version(user, builds, store=storage)
    versions.switch_version(user, first.id, expected_revision=0, store=storage)
    pages = [client.get(BASE, headers=user_headers, params={"limit": 1, "offset": i}).json()["data"] for i in range(2)]
    assert all(page["total"] == 2 for page in pages)
    assert {page["items"][0]["id"] for page in pages} == {first.id, second.id}
    assert sum(page["items"][0]["is_active"] for page in pages) == 1
    detail = client.get(BASE + "/" + first.id, headers=user_headers)
    data = detail.json()["data"]
    assert data["manifest_integrity"] == "valid" and data["document_count"] == 2
    assert {doc["id"] for doc in data["documents"]} == set(docs)
    assert {m["build_id"] for m in data["members"]} == set(builds)
    for hidden in ("endpoint", "https://model.example", "namespace", "manifest_json", "secret"):
        assert hidden not in detail.text
    assert client.get(BASE + "/active", headers=user_headers).json()["data"]["version_id"] == first.id
    assert client.get(BASE, headers=user_headers, params={"limit": 101}).status_code == 400


def test_history_is_owner_scoped(client, user_headers, admin_headers, complete):
    version = complete[3]
    assert client.get(BASE, headers=admin_headers).json()["data"]["total"] == 0
    wrong = client.get(BASE + "/" + version.id, headers=admin_headers)
    missing = client.get(BASE + "/missing", headers=admin_headers)
    assert wrong.status_code == missing.status_code == 404 and wrong.json() == missing.json()


def test_changed_documents_and_corrupt_history_remain_discoverable(client, user_headers, complete, monkeypatch):
    user, _, docs, version, _ = complete
    with SessionLocal() as db:
        db.get(Document, docs[0]).file_name = "renamed.txt"
        db.commit()
    monkeypatch.setattr(versions, "get_vector_store", lambda: pytest.fail("history must not open vectors"))
    data = client.get(BASE + "/" + version.id, headers=user_headers).json()["data"]
    assert data["manifest_integrity"] == "valid"
    assert "renamed.txt" not in str(data)
    with SessionLocal() as db:
        db.get(IndexVersion, version.id).manifest_sha256 = "damaged"
        db.commit()
    data = client.get(BASE, headers=user_headers).json()["data"]
    assert data["total"] == 1 and data["items"][0]["manifest_integrity"] == "invalid"
    assert versions.active_state(user) == (None, 0)


def test_management_worker_activation_history_rollback(client, user_headers, ready_task, monkeypatch):
    user, task, config, _, model = ready_task
    monkeypatch.setattr(model, "embed_query", lambda self, text: [1., 2., 3.], raising=False)
    monkeypatch.setattr(versions, "RemoteEmbeddingAdapter", model)
    config.retrieval_top_n = 5
    first = execute_configured_rebuild(user, task)
    assert first.status == "ready"
    assert client.put(BASE + "/active", headers=user_headers, json={"version_id": first.version_id, "expected_revision": 0}).status_code == 200
    second_task = create(client, user_headers)
    second = execute_configured_rebuild(user, second_task["id"])
    assert second.status == "ready"
    assert client.put(BASE + "/active", headers=user_headers, json={"version_id": second.version_id, "expected_revision": 1}).status_code == 200
    history = client.get(BASE, headers=user_headers).json()["data"]
    old = next(item for item in history["items"] if item["id"] == first.version_id)
    assert not old["is_active"]
    assert client.get(BASE + "/" + old["id"], headers=user_headers).status_code == 200
    assert client.put(BASE + "/active", headers=user_headers, json={"version_id": old["id"], "expected_revision": 2}).status_code == 200
    assert versions.search_active(user, "evidence", config)
