import hashlib
import json

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.index_version import IndexVersion, IndexSwitch
from app.services import index_version_service as versions
from app.services.embedding_service import EmbeddingError
from test_chunking_integration import storage
from test_index_versions import complete


@pytest.mark.parametrize("damage", ["missing", "array", "member", "schema", "digest", "duplicate"])
def test_structural_corruption_is_not_missing_version(client, user_headers, complete, storage, damage):
    user, builds, _, old, config = complete
    versions.switch_version(user, old.id, expected_revision=0, store=storage)
    target = versions.create_version(user, builds, store=storage)
    with SessionLocal() as db:
        row = db.get(IndexVersion, target.id)
        data = json.loads(row.manifest_json)
        if damage == "missing":
            del data["members"]
        elif damage == "array":
            data = []
        elif damage == "member":
            del data["members"][0]["namespace"]
        elif damage == "schema":
            data["schema"] = "unknown"
        elif damage == "digest":
            data["members"][0]["records_sha256"] = "not-a-digest"
        else:
            data["members"][1]["build_id"] = data["members"][0]["build_id"]
        row.manifest_json = json.dumps(data)
        # Matching hash alone must not make malformed stored data acceptable.
        row.manifest_sha256 = hashlib.sha256(row.manifest_json.encode()).hexdigest()
        db.commit()
    detail = client.get("/api/v1/index-versions/" + target.id, headers=user_headers)
    assert detail.status_code == 200 and detail.json()["data"]["manifest_integrity"] == "invalid"
    response = client.put("/api/v1/index-versions/active", headers=user_headers,
        json={"version_id": target.id, "expected_revision": 1})
    assert response.status_code == 400, response.text
    assert versions.active_state(user) == (old.id, 1)
    assert versions.search_active(user, "evidence", config, store=storage)
    with SessionLocal() as db:
        assert len(list(db.scalars(select(IndexSwitch)))) == 1


def test_corrupt_active_fails_closed_but_can_deactivate(client, user_headers, complete, storage):
    user, _, _, version, config = complete
    versions.switch_version(user, version.id, expected_revision=0, store=storage)
    with SessionLocal() as db:
        row = db.get(IndexVersion, version.id)
        row.manifest_json = "{}"
        row.manifest_sha256 = hashlib.sha256(b"{}").hexdigest()
        db.commit()
    with pytest.raises(EmbeddingError):
        versions.search_active(user, "evidence", config, store=storage)
    response = client.put("/api/v1/index-versions/active", headers=user_headers,
        json={"version_id": None, "expected_revision": 1})
    assert response.status_code == 200 and versions.active_state(user) == (None, 2)
