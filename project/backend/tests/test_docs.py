"""知识库模块测试（api_document 第 3 章 / PRD 4.2）。"""

from __future__ import annotations

import io

from app.core.database import SessionLocal
from app.models.document import Document
from app.services import vector_store

SAMPLE_TEXT = (
    "自注意力机制是 Transformer 架构的核心组件。"
    "它能够建立序列中任意两个位置之间的直接联系，从而有效捕捉长距离依赖。"
    "多头注意力则让模型在不同的表示子空间中并行关注不同的信息。"
) * 5


def upload_text_file(client, headers, name="paper.txt", content=SAMPLE_TEXT):
    return client.post(
        "/api/v1/docs/upload",
        headers=headers,
        files=[("files", (name, io.BytesIO(content.encode("utf-8")), "text/plain"))],
    )


def test_upload_txt_completes_full_pipeline(client, user_headers):
    body = upload_text_file(client, user_headers).json()
    assert body["code"] == 200
    assert len(body["data"]) == 1
    doc_id = body["data"][0]["id"]

    # 同步处理模式下，返回时状态已流转到 ready
    with SessionLocal() as db:
        document = db.get(Document, doc_id)
        assert document.status == "ready"
        assert document.file_size > 0
        # 向量已写入该用户专属 Collection
        assert vector_store.get_vector_store().count(document.user_id) > 0


def test_upload_rejects_unsupported_extension(client, user_headers):
    body = client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("virus.exe", io.BytesIO(b"MZ..."), "application/octet-stream"))],
    ).json()
    assert body["code"] == 400
    assert "格式不支持" in body["message"]


def test_upload_rejects_too_many_files(client, user_headers):
    files = [
        ("files", (f"f{i}.txt", io.BytesIO(b"hello world content"), "text/plain"))
        for i in range(11)
    ]
    body = client.post("/api/v1/docs/upload", headers=user_headers, files=files).json()
    assert body["code"] == 400
    assert "10" in body["message"]


def test_upload_requires_authentication(client):
    body = client.post(
        "/api/v1/docs/upload",
        files=[("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))],
    ).json()
    assert body["code"] == 401


def test_list_documents_pagination_and_filter(client, user_headers):
    for i in range(3):
        upload_text_file(client, user_headers, name=f"doc{i}.txt")

    body = client.get("/api/v1/docs/list?page=1&page_size=2", headers=user_headers).json()
    assert body["code"] == 200
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 2
    assert body["data"]["items"][0]["status_label"]  # 中文状态文案

    ready = client.get("/api/v1/docs/list?status=ready", headers=user_headers).json()
    assert ready["data"]["total"] == 3

    empty = client.get("/api/v1/docs/list?status=failed", headers=user_headers).json()
    assert empty["data"]["total"] == 0


def test_list_documents_rejects_invalid_status(client, user_headers):
    body = client.get("/api/v1/docs/list?status=unknown", headers=user_headers).json()
    assert body["code"] == 400


def test_delete_document_clears_vectors_and_metadata(client, user_headers):
    doc_id = upload_text_file(client, user_headers).json()["data"][0]["id"]

    with SessionLocal() as db:
        user_id = db.get(Document, doc_id).user_id
    store = vector_store.get_vector_store()
    assert store.count(user_id) > 0

    body = client.delete(f"/api/v1/docs/{doc_id}", headers=user_headers).json()
    assert body["code"] == 200

    with SessionLocal() as db:
        assert db.get(Document, doc_id) is None
    # [S-3] 向量片段同步清理，向量库不留垃圾数据
    assert store.count(user_id) == 0


def test_cannot_delete_other_users_document(client, user_headers):
    doc_id = upload_text_file(client, user_headers).json()["data"][0]["id"]

    client.post("/api/v1/auth/register", json={"email": "other@qq.com", "password": "abc123"})
    other_token = client.post(
        "/api/v1/auth/login", json={"email": "other@qq.com", "password": "abc123"}
    ).json()["data"]["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # 水平越权防御：返回 404 而非 403，避免文档 ID 被探测
    assert client.delete(f"/api/v1/docs/{doc_id}", headers=other_headers).json()["code"] == 404
    # 他人的列表中也看不到该文档
    assert client.get("/api/v1/docs/list", headers=other_headers).json()["data"]["total"] == 0


def test_failed_document_is_marked(client, user_headers):
    """空内容文件应被拒绝；无法解析的内容标记为 failed。"""
    body = client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("empty.txt", io.BytesIO(b"   \n  "), "text/plain"))],
    ).json()
    assert body["code"] == 200
    doc_id = body["data"][0]["id"]
    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "failed"


def test_retry_failed_document(client, user_headers):
    body = client.post(
        "/api/v1/docs/upload",
        headers=user_headers,
        files=[("files", ("empty.txt", io.BytesIO(b"   \n  "), "text/plain"))],
    ).json()
    doc_id = body["data"][0]["id"]

    retried = client.post(f"/api/v1/docs/{doc_id}/retry", headers=user_headers).json()
    assert retried["code"] == 200
    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "failed"

    ready_id = upload_text_file(client, user_headers).json()["data"][0]["id"]
    rejected = client.post(f"/api/v1/docs/{ready_id}/retry", headers=user_headers).json()
    assert rejected["code"] == 400
