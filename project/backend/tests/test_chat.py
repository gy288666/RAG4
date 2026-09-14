"""智能问答与会话管理测试（api_document 第 4 章 / PRD 4.3、4.4）。"""

from __future__ import annotations

import io
import json

from app.core.database import SessionLocal
from app.models.chat import ChatMessage, ChatSession

DOC_TEXT = (
    "自注意力机制是 Transformer 架构的核心组件，能够建立序列中任意两个位置之间的直接联系。"
    "相比循环神经网络，它具备更强的并行能力与长距离依赖建模能力。"
) * 4


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    """把 SSE 原始报文解析为 ``[(event, data), ...]``。"""
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if event is not None:
            events.append((event, data or {}))
    return events


def create_session(client, headers) -> str:
    body = client.post("/api/v1/chat/session", headers=headers).json()
    assert body["code"] == 200
    return body["data"]["session_id"]


def ask(client, headers, session_id: str, query: str, enable_rag: bool = True):
    response = client.post(
        "/api/v1/chat/query",
        headers=headers,
        json={"session_id": session_id, "query": query, "enable_rag": enable_rag},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def upload_doc(client, headers):
    return client.post(
        "/api/v1/docs/upload",
        headers=headers,
        files=[("files", ("transformer.txt", io.BytesIO(DOC_TEXT.encode()), "text/plain"))],
    )


# ------------------------------------------------------------
# 会话 CRUD
# ------------------------------------------------------------


def test_create_and_rename_session(client, user_headers):
    session_id = create_session(client, user_headers)

    body = client.put(
        f"/api/v1/chat/session/{session_id}",
        headers=user_headers,
        json={"title": "Transformer 论文精读"},
    ).json()
    assert body["code"] == 200
    assert body["data"]["title"] == "Transformer 论文精读"


def test_session_list_search_and_delete(client, user_headers):
    first = create_session(client, user_headers)
    second = create_session(client, user_headers)
    client.put(f"/api/v1/chat/session/{first}", headers=user_headers, json={"title": "注意力机制"})
    client.put(f"/api/v1/chat/session/{second}", headers=user_headers, json={"title": "扩散模型"})

    body = client.get("/api/v1/chat/sessions", headers=user_headers).json()
    assert body["data"]["total"] == 2

    # 标题模糊搜索
    found = client.get("/api/v1/chat/sessions?keyword=注意力", headers=user_headers).json()
    assert found["data"]["total"] == 1
    assert found["data"]["items"][0]["title"] == "注意力机制"

    assert client.delete(f"/api/v1/chat/session/{first}", headers=user_headers).json()["code"] == 200
    assert client.get("/api/v1/chat/sessions", headers=user_headers).json()["data"]["total"] == 1

    with SessionLocal() as db:
        assert db.get(ChatSession, first).is_deleted == 1  # 逻辑删除


def test_cannot_access_other_users_session(client, user_headers):
    session_id = create_session(client, user_headers)

    client.post("/api/v1/auth/register", json={"email": "intruder@qq.com", "password": "abc123"})
    token = client.post(
        "/api/v1/auth/login", json={"email": "intruder@qq.com", "password": "abc123"}
    ).json()["data"]["access_token"]
    other = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v1/chat/session/{session_id}/messages", headers=other).json()["code"] == 404
    assert client.put(
        f"/api/v1/chat/session/{session_id}", headers=other, json={"title": "hack"}
    ).json()["code"] == 404
    assert client.delete(f"/api/v1/chat/session/{session_id}", headers=other).json()["code"] == 404


# ------------------------------------------------------------
# SSE 问答
# ------------------------------------------------------------


def test_rag_query_returns_chunk_title_and_done(client, user_headers):
    upload_doc(client, user_headers)
    session_id = create_session(client, user_headers)

    events = ask(client, user_headers, session_id, "自注意力机制的作用是什么？")
    names = [name for name, _ in events]

    assert "chunk" in names
    assert names[-1] == "done"
    assert "title" in names  # 首轮提问自动生成标题

    done = events[-1][1]
    assert done["message_id"].startswith("msg_")
    assert isinstance(done["citations"], list) and done["citations"]
    assert done["warnings"] == []

    # [I-3] 引用条目字段完整
    citation = done["citations"][0]
    for field in ("index", "doc_name", "page", "chunk_index", "snippet"):
        assert field in citation
    assert citation["doc_name"] == "transformer.txt"
    assert citation["page"] is None  # TXT 无页码，前端改用 chunk_index


def test_first_round_title_is_persisted(client, user_headers):
    session_id = create_session(client, user_headers)
    events = ask(client, user_headers, session_id, "什么是检索增强生成？", enable_rag=False)
    titles = [data for name, data in events if name == "title"]
    assert titles and titles[0]["session_id"] == session_id

    with SessionLocal() as db:
        assert db.get(ChatSession, session_id).title != "新对话"


def test_plain_mode_skips_retrieval(client, user_headers):
    """[S-4] enable_rag=false：无检索、citations 为 []，数据库中存 NULL。"""
    upload_doc(client, user_headers)
    session_id = create_session(client, user_headers)

    events = ask(client, user_headers, session_id, "你好，请介绍一下你自己", enable_rag=False)
    done = events[-1][1]
    assert events[-1][0] == "done"
    assert done["citations"] == []
    assert done["warnings"] == []

    with SessionLocal() as db:
        assistant = (
            db.query(ChatMessage)
            .filter_by(session_id=session_id, role="assistant")
            .one()
        )
        assert assistant.citations is None


def test_messages_are_persisted_and_readable(client, user_headers):
    upload_doc(client, user_headers)
    session_id = create_session(client, user_headers)
    ask(client, user_headers, session_id, "自注意力机制的作用是什么？")

    body = client.get(f"/api/v1/chat/session/{session_id}/messages", headers=user_headers).json()
    assert body["code"] == 200
    messages = body["data"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["citations"]


def test_multi_turn_keeps_context(client, user_headers):
    session_id = create_session(client, user_headers)
    ask(client, user_headers, session_id, "什么是 RAG？", enable_rag=False)
    ask(client, user_headers, session_id, "它有哪些优势？", enable_rag=False)

    body = client.get(f"/api/v1/chat/session/{session_id}/messages", headers=user_headers).json()
    assert len(body["data"]) == 4


def test_session_list_shows_last_message_preview(client, user_headers):
    """[I-2] 列表返回最新一条 assistant 消息的前 60 字。"""
    session_id = create_session(client, user_headers)
    ask(client, user_headers, session_id, "什么是向量检索？", enable_rag=False)

    items = client.get("/api/v1/chat/sessions", headers=user_headers).json()["data"]["items"]
    preview = next(i for i in items if i["session_id"] == session_id)["last_message_preview"]
    assert preview
    assert len(preview) <= 60


def test_query_rejects_empty_and_unknown_session(client, user_headers):
    session_id = create_session(client, user_headers)
    assert client.post(
        "/api/v1/chat/query",
        headers=user_headers,
        json={"session_id": session_id, "query": "   "},
    ).json()["code"] == 400

    assert client.post(
        "/api/v1/chat/query",
        headers=user_headers,
        json={"session_id": "sess_not_exist", "query": "你好"},
    ).json()["code"] == 404


def test_query_without_documents_still_answers(client, user_headers):
    """知识库为空时不应报错，模型按提示词回答“无法回答”。"""
    session_id = create_session(client, user_headers)
    events = ask(client, user_headers, session_id, "论文的主要贡献是什么？")
    assert events[-1][0] == "done"
    assert events[-1][1]["citations"] == []
