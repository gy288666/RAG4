"""管理员后台测试（api_document 第 5 章 / PRD 4.5、5.2）。"""

from __future__ import annotations

import io

from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import config_service


# ------------------------------------------------------------
# 权限校验
# ------------------------------------------------------------


def test_admin_endpoints_reject_normal_user(client, user_headers):
    for method, path in [
        ("get", "/api/v1/admin/users"),
        ("get", "/api/v1/admin/configs"),
        ("get", "/api/v1/admin/stats"),
        ("get", "/api/v1/admin/reset-requests"),
    ]:
        body = getattr(client, method)(path, headers=user_headers).json()
        assert body["code"] == 403, path


def test_admin_endpoints_reject_anonymous(client):
    assert client.get("/api/v1/admin/users").json()["code"] == 401


# ------------------------------------------------------------
# 用户管理
# ------------------------------------------------------------


def test_list_users_includes_doc_count(client, admin_headers, user_headers):
    client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("a.txt", io.BytesIO(("知识库内容测试。" * 30).encode()), "text/plain"))],
    )
    body = client.get("/api/v1/admin/users", headers=admin_headers).json()
    assert body["code"] == 200
    target = next(i for i in body["data"]["items"] if i["email"] == "student@outlook.com")
    assert target["doc_count"] == 1
    assert target["role"] == "user"
    assert target["last_login_at"]


def test_search_users_by_keyword(client, admin_headers, user_headers):
    body = client.get("/api/v1/admin/users?keyword=student", headers=admin_headers).json()
    assert body["data"]["total"] == 1


def test_update_role_and_status(client, admin_headers, user_headers):
    with SessionLocal() as db:
        user_id = db.query(User).filter_by(email="student@outlook.com").one().id

    body = client.put(
        f"/api/v1/admin/users/{user_id}/role-status",
        headers=admin_headers,
        json={"role": "admin", "status": 1},
    ).json()
    assert body["code"] == 200

    with SessionLocal() as db:
        assert db.get(User, user_id).role == "admin"

    # 禁用后该用户的 Token 立即不可用（403）
    client.put(
        f"/api/v1/admin/users/{user_id}/role-status",
        headers=admin_headers,
        json={"status": 0},
    )
    assert client.get("/api/v1/auth/me", headers=user_headers).json()["code"] == 403
    # 且无法再次登录
    assert client.post(
        "/api/v1/auth/login", json={"email": "student@outlook.com", "password": "pwd123456"}
    ).json()["code"] == 403


def test_admin_cannot_disable_self(client, admin_headers):
    with SessionLocal() as db:
        admin_id = db.query(User).filter_by(email="root@outlook.com").one().id

    body = client.put(
        f"/api/v1/admin/users/{admin_id}/role-status", headers=admin_headers, json={"status": 0}
    ).json()
    assert body["code"] == 400


def test_update_role_validates_values(client, admin_headers, user_headers):
    with SessionLocal() as db:
        user_id = db.query(User).filter_by(email="student@outlook.com").one().id

    assert client.put(
        f"/api/v1/admin/users/{user_id}/role-status",
        headers=admin_headers,
        json={"role": "superuser"},
    ).json()["code"] == 400
    assert client.put(
        f"/api/v1/admin/users/{user_id}/role-status", headers=admin_headers, json={}
    ).json()["code"] == 400
    assert client.put(
        "/api/v1/admin/users/999999/role-status", headers=admin_headers, json={"status": 1}
    ).json()["code"] == 404


# ------------------------------------------------------------
# 密码重置闭环
# ------------------------------------------------------------


def test_reset_password_flow(client, admin_headers, user_headers):
    """用户申请 → 管理员列表可见 → 重置 → 旧 Token 失效 → 临时密码可登录。"""
    client.post("/api/v1/auth/reset-request", json={"email": "student@outlook.com"})

    requests = client.get("/api/v1/admin/reset-requests", headers=admin_headers).json()
    assert requests["code"] == 200
    entry = next(r for r in requests["data"] if r["email"] == "student@outlook.com")
    assert entry["is_handled"] == 0
    user_id = entry["user_id"]
    assert user_id is not None

    body = client.put(
        f"/api/v1/admin/users/{user_id}/reset-password", headers=admin_headers
    ).json()
    assert body["code"] == 200
    temporary_password = body["data"]["temporary_password"]
    assert temporary_password.startswith("Temp_")

    # [S-2] 重置后旧 JWT 立即失效
    assert client.get("/api/v1/auth/me", headers=user_headers).json()["code"] == 401

    # 临时密码可登录
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "student@outlook.com", "password": temporary_password},
    ).json()["code"] == 200

    # 申请已被标记为处理完毕，待处理列表清空
    remaining = client.get("/api/v1/admin/reset-requests", headers=admin_headers).json()["data"]
    assert all(r["email"] != "student@outlook.com" for r in remaining)


# ------------------------------------------------------------
# 系统配置 [S-1]
# ------------------------------------------------------------


def test_get_configs_masks_api_keys(client, admin_headers):
    client.put(
        "/api/v1/admin/configs",
        headers=admin_headers,
        json={"llm": {"api_key": "sk-super-secret-value-1234"}},
    )
    body = client.get("/api/v1/admin/configs", headers=admin_headers).json()
    assert body["code"] == 200

    masked = body["data"]["llm"]["api_key_masked"]
    assert "****" in masked
    assert "super-secret" not in masked
    # 整个响应体中不得出现明文 Key
    assert "sk-super-secret-value-1234" not in client.get(
        "/api/v1/admin/configs", headers=admin_headers
    ).text


def test_api_key_is_encrypted_at_rest(client, admin_headers):
    plaintext = "rerank-key-abcdefg-7890"
    client.put(
        "/api/v1/admin/configs",
        headers=admin_headers,
        json={"rerank": {"api_key": plaintext}},
    )
    with SessionLocal() as db:
        stored = db.get(SystemConfig, config_service.RERANK_API_KEY).config_value
    # 落库的是 AES-256 密文，且可正确解密回明文
    assert stored != plaintext
    assert stored.startswith("enc::v1::")
    assert decrypt_secret(stored) == plaintext


def test_update_chunking_takes_effect_immediately(client, admin_headers):
    body = client.put(
        "/api/v1/admin/configs",
        headers=admin_headers,
        json={"chunking": {"chunk_size": 800, "overlap": 80}},
    ).json()
    assert body["code"] == 200

    configs = client.get("/api/v1/admin/configs", headers=admin_headers).json()["data"]
    assert configs["chunking"] == {"chunk_size": 800, "overlap": 80}

    with SessionLocal() as db:
        runtime = config_service.load_runtime_config(db)
        assert runtime.chunk_size == 800
        assert runtime.chunk_overlap == 80


def test_update_configs_validates_overlap(client, admin_headers):
    body = client.put(
        "/api/v1/admin/configs",
        headers=admin_headers,
        json={"chunking": {"chunk_size": 300, "overlap": 400}},
    ).json()
    assert body["code"] == 400

    assert client.put("/api/v1/admin/configs", headers=admin_headers, json={}).json()["code"] == 400


def test_empty_api_key_does_not_clear_existing(client, admin_headers):
    """前端回显掩码时提交空串，不应把已配置的 Key 清空。"""
    client.put(
        "/api/v1/admin/configs", headers=admin_headers, json={"llm": {"api_key": "sk-keep-me-123"}}
    )
    client.put(
        "/api/v1/admin/configs",
        headers=admin_headers,
        json={"llm": {"api_key": "", "model": "new-model"}},
    )
    with SessionLocal() as db:
        assert config_service.get_secret(db, config_service.LLM_API_KEY) == "sk-keep-me-123"
        assert config_service.get(db, config_service.LLM_MODEL) == "new-model"


# ------------------------------------------------------------
# 运行监控 [I-4]
# ------------------------------------------------------------


def test_stats_reflects_usage(client, admin_headers, user_headers):
    client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("s.txt", io.BytesIO(("统计测试内容。" * 40).encode()), "text/plain"))],
    )
    session_id = client.post("/api/v1/chat/session", headers=user_headers).json()["data"][
        "session_id"
    ]
    client.post(
        "/api/v1/chat/query",
        headers=user_headers,
        json={"session_id": session_id, "query": "统计一下", "enable_rag": True},
    )

    body = client.get("/api/v1/admin/stats?days=7", headers=admin_headers).json()
    assert body["code"] == 200
    data = body["data"]
    assert data["period_days"] == 7
    assert data["total_llm_calls"] >= 1
    assert data["total_vector_searches"] >= 1
    assert data["total_tokens_used"] > 0
    assert data["failure_rate"].endswith("%")
    assert isinstance(data["ocr_failed_queue"], list)
    assert isinstance(data["daily_trend"], list)


def test_stats_ocr_failed_queue(client, admin_headers, user_headers):
    """解析失败的文档应出现在失败队列中，并可回溯到 doc_id 与文件名。"""
    doc_id = client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("broken.txt", io.BytesIO(b"  \n "), "text/plain"))],
    ).json()["data"][0]["id"]

    queue = client.get("/api/v1/admin/stats", headers=admin_headers).json()["data"][
        "ocr_failed_queue"
    ]
    entry = next(item for item in queue if item["doc_id"] == doc_id)
    assert entry["file_name"] == "broken.txt"
    assert entry["error"]
