"""认证模块测试（api_document 第 2 章 / PRD 4.1）。"""

from __future__ import annotations

from datetime import timedelta

from app.core.database import SessionLocal
from app.models.reset_request import PasswordResetRequest
from app.utils.datetime_utils import now


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register", json={"email": "newbie@qq.com", "password": "abc123"}
    )
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["email"] == "newbie@qq.com"
    assert body["data"]["created_at"]


def test_register_rejects_invalid_email_domain(client):
    response = client.post(
        "/api/v1/auth/register", json={"email": "hacker@evil-domain.xyz", "password": "abc123"}
    )
    assert response.json()["code"] == 400


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/register", json={"email": "someone@163.com", "password": "123"}
    )
    body = response.json()
    assert body["code"] == 400
    assert "6" in body["message"]


def test_register_rejects_duplicate_email(client):
    payload = {"email": "dup@gmail.com", "password": "abc123"}
    client.post("/api/v1/auth/register", json=payload)
    assert client.post("/api/v1/auth/register", json=payload).json()["code"] == 400


def test_login_returns_jwt_and_user_info(client):
    client.post("/api/v1/auth/register", json={"email": "a@qq.com", "password": "abc123"})
    body = client.post(
        "/api/v1/auth/login", json={"email": "a@qq.com", "password": "abc123"}
    ).json()
    assert body["code"] == 200
    assert body["data"]["token_type"] == "Bearer"
    assert body["data"]["expires_in"] == 7 * 24 * 3600  # PRD：默认 7 天
    assert body["data"]["user_info"]["role"] == "user"


def test_login_distinguishes_error_reasons(client):
    client.post("/api/v1/auth/register", json={"email": "b@qq.com", "password": "abc123"})
    assert "邮箱未注册" in client.post(
        "/api/v1/auth/login", json={"email": "nobody@qq.com", "password": "abc123"}
    ).json()["message"]
    assert "密码错误" in client.post(
        "/api/v1/auth/login", json={"email": "b@qq.com", "password": "wrongpwd"}
    ).json()["message"]


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/v1/auth/me").json()["code"] == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token"}).json()["code"]
        == 401
    )


def test_me_returns_current_user(client, user_headers):
    body = client.get("/api/v1/auth/me", headers=user_headers).json()
    assert body["code"] == 200
    assert body["data"]["email"] == "student@outlook.com"


# ------------------------------------------------------------
# 密码重置申请频率限制 [M-4]
# ------------------------------------------------------------


def test_reset_request_rate_limited(client):
    payload = {"email": "reset-me@qq.com"}
    assert client.post("/api/v1/auth/reset-request", json=payload).json()["code"] == 200

    second = client.post("/api/v1/auth/reset-request", json=payload).json()
    assert second["code"] == 400
    assert "10 分钟" in second["message"]


def test_reset_request_allowed_after_window(client):
    payload = {"email": "later@qq.com"}
    client.post("/api/v1/auth/reset-request", json=payload)

    with SessionLocal() as db:
        record = db.query(PasswordResetRequest).filter_by(email="later@qq.com").one()
        record.last_request_at = now() - timedelta(minutes=11)
        db.commit()

    assert client.post("/api/v1/auth/reset-request", json=payload).json()["code"] == 200

    with SessionLocal() as db:
        # 同邮箱不应堆积多条待处理记录，只刷新时间
        assert db.query(PasswordResetRequest).filter_by(email="later@qq.com").count() == 1


# ------------------------------------------------------------
# token_version 主动失效 [S-2]
# ------------------------------------------------------------


def test_change_password_invalidates_old_token(client, user_headers):
    old_token = user_headers["Authorization"]

    body = client.post(
        "/api/v1/auth/change-password",
        headers=user_headers,
        json={"old_password": "pwd123456", "new_password": "newpwd123"},
    ).json()
    assert body["code"] == 200
    new_token = body["data"]["access_token"]

    # 旧 Token 立即失效
    assert client.get("/api/v1/auth/me", headers={"Authorization": old_token}).json()["code"] == 401
    # 新 Token 可用
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}).json()[
            "code"
        ]
        == 200
    )
    # 新密码可登录
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "student@outlook.com", "password": "newpwd123"}
        ).json()["code"]
        == 200
    )


def test_change_password_rejects_wrong_old_password(client, user_headers):
    body = client.post(
        "/api/v1/auth/change-password",
        headers=user_headers,
        json={"old_password": "wrong-one", "new_password": "newpwd123"},
    ).json()
    assert body["code"] == 400
