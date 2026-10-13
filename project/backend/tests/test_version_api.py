import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.index_version import IndexSwitch, IndexVersion
from app.services import index_version_service as versions
from test_chunking_integration import storage
from test_index_versions import complete

URL = "/api/v1/index-versions/active"


def switch(client, headers, version, revision):
    return client.put(URL, headers=headers, json={"version_id": version, "expected_revision": revision})


@pytest.mark.parametrize("method", ["get", "put"])
def test_auth_required(client, method):
    assert getattr(client, method)(URL).status_code == 401


@pytest.mark.parametrize("body", [{"expected_revision": 0}, {"version_id": None},
    {"version_id": None, "expected_revision": -1}, {"version_id": None, "expected_revision": True},
    {"version_id": None, "expected_revision": 0, "user_id": 1}])
def test_explicit_valid_cas_required(client, user_headers, body):
    assert client.put(URL, headers=user_headers, json=body).status_code == 400
    assert client.get(URL, headers=user_headers).json()["data"] == {"version_id": None, "revision": 0}


def test_activate_rollback_deactivate_and_audit(client, user_headers, complete, storage):
    user, builds, _, first, config = complete
    second = versions.create_version(user, builds, store=storage)
    assert client.get(URL, headers=user_headers).json()["data"]["revision"] == 0
    for revision, target in enumerate([first.id, second.id, first.id, None]):
        result = switch(client, user_headers, target, revision)
        assert result.status_code == 200, result.text
        assert result.json()["data"] == {"version_id": target, "revision": revision + 1}
        if target:
            assert versions.search_active(user, "evidence", config, store=storage)
    with SessionLocal() as db:
        rows = list(db.scalars(select(IndexSwitch).where(IndexSwitch.user_id == user)))
        assert len(rows) == 4


def test_stale_request_cannot_overwrite_active(client, user_headers, complete):
    user, _, _, version, _ = complete
    assert switch(client, user_headers, version.id, 0).status_code == 200
    for target in (version.id, None):
        assert switch(client, user_headers, target, 0).status_code == 409
    assert versions.active_state(user) == (version.id, 1)


def test_foreign_version_same_as_missing(client, user_headers, admin_headers, complete):
    _, _, _, version, _ = complete
    wrong = switch(client, admin_headers, version.id, 0)
    missing = switch(client, admin_headers, "missing", 0)
    assert wrong.status_code == missing.status_code == 404
    assert wrong.json() == missing.json()
    assert client.get(URL, headers=user_headers).json()["data"]["revision"] == 0
    assert client.get(URL, headers=admin_headers).json()["data"]["revision"] == 0


def test_corrupt_candidate_preserves_previous_pointer(client, user_headers, complete, storage):
    user, builds, _, version, _ = complete
    assert switch(client, user_headers, version.id, 0).status_code == 200
    other = versions.create_version(user, builds, store=storage)
    with SessionLocal() as db:
        db.get(IndexVersion, other.id).manifest_sha256 = "bad"
        db.commit()
    assert switch(client, user_headers, other.id, 1).status_code == 400
    assert versions.active_state(user) == (version.id, 1)
    with SessionLocal() as db:
        assert len(list(db.scalars(select(IndexSwitch)))) == 1


def test_deactivate_without_vector_backend(client, user_headers, complete, monkeypatch):
    user, _, _, version, _ = complete
    assert switch(client, user_headers, version.id, 0).status_code == 200
    def unavailable():
        raise RuntimeError("vector backend unavailable")
    monkeypatch.setattr(versions, "get_vector_store", unavailable)
    assert switch(client, user_headers, None, 1).status_code == 200
    assert versions.active_state(user) == (None, 2)
