"""智能问答模块 ``/api/v1/chat``（api_document 第 4 章）。"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user
from app.core.response import BadRequest, NotFound, success
from app.models.chat import ROLE_ASSISTANT, ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatQueryRequest, SessionTitleUpdate
from app.services import rag_service
from app.utils.datetime_utils import fmt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["智能问答"])

PREVIEW_LENGTH = 60


def _get_owned_session(db: Session, session_id: str, user: User) -> ChatSession:
    """获取会话并校验归属，杜绝水平越权（PRD 5.2）。"""
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id or session.is_deleted == 1:
        raise NotFound("会话不存在或无权访问")
    return session


@router.post("/session", summary="创建新会话")
def create_session(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = ChatSession(
        id=rag_service.new_id("sess"), user_id=user.id, title=rag_service.DEFAULT_TITLE
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return success(
        {
            "session_id": session.id,
            "title": session.title,
            "created_at": fmt(session.created_at),
        },
        message="会话创建成功",
    )


@router.put("/session/{session_id}", summary="修改会话标题")
def rename_session(
    session_id: str,
    payload: SessionTitleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user)
    title = (payload.title or "").strip()
    if not title:
        raise BadRequest("标题不能为空")

    session.title = title[:255]
    db.add(session)
    db.commit()
    db.refresh(session)
    return success(
        {
            "session_id": session.id,
            "title": session.title,
            "updated_at": fmt(session.updated_at),
        },
        message="修改成功",
    )


@router.get("/sessions", summary="获取会话列表")
def list_sessions(
    keyword: str | None = Query(None, description="按标题模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conditions = [ChatSession.user_id == user.id, ChatSession.is_deleted == 0]
    if keyword and keyword.strip():
        conditions.append(ChatSession.title.like(f"%{keyword.strip()}%"))

    total = db.execute(select(func.count(ChatSession.id)).where(*conditions)).scalar_one()
    sessions = (
        db.execute(
            select(ChatSession)
            .where(*conditions)
            .order_by(
                ChatSession.updated_at.desc(),
                ChatSession.created_at.desc(),
                ChatSession.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    # [I-2] 各会话最新一条 assistant 消息正文的前 60 字
    previews: dict[str, str] = {}
    if sessions:
        rows = db.execute(
            select(ChatMessage.session_id, ChatMessage.content, ChatMessage.created_at)
            .where(
                ChatMessage.session_id.in_([s.id for s in sessions]),
                ChatMessage.role == ROLE_ASSISTANT,
            )
            .order_by(ChatMessage.created_at.asc())
        ).all()
        for session_id, content, _ in rows:
            previews[session_id] = (content or "").replace("\n", " ")[:PREVIEW_LENGTH]

    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "session_id": s.id,
                    "title": s.title,
                    "last_message_preview": previews.get(s.id, ""),
                    "created_at": fmt(s.created_at),
                    "updated_at": fmt(s.updated_at),
                }
                for s in sessions
            ],
        },
        message="获取成功",
    )


@router.delete("/session/{session_id}", summary="删除会话")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, user)
    # 逻辑删除，保留历史消息便于审计（PRD 4.4.3）
    session.is_deleted = 1
    db.add(session)
    db.commit()
    return success(None, message="会话已删除")


@router.get("/session/{session_id}/messages", summary="获取历史消息记录")
def list_messages(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_owned_session(db, session_id, user)
    messages = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        .scalars()
        .all()
    )
    return success(
        [
            {
                "message_id": m.id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations,
                "created_at": fmt(m.created_at),
            }
            for m in messages
        ],
        message="获取成功",
    )


# ------------------------------------------------------------
# SSE 流式问答
# ------------------------------------------------------------


def sse_frame(event: str, data: dict) -> str:
    """按 SSE 规范编码单帧报文。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_stream(user_id: int, session_id: str, query: str, enable_rag: bool) -> Iterator[str]:
    """在独立数据库会话中执行问答。

    StreamingResponse 的生成体在依赖注入的会话关闭之后才被消费，
    因此这里必须自行创建并管理 Session 生命周期。
    """
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        session = db.get(ChatSession, session_id)
        if user is None or session is None:
            yield sse_frame("error", {"code": 404, "message": "会话不存在或无权访问"})
            return
        for event, payload in rag_service.stream_answer(db, user, session, query, enable_rag):
            yield sse_frame(event, payload)
    except Exception as exc:  # pragma: no cover - 兜底，保证前端总能收到终止帧
        logger.exception("SSE 问答异常: %s", exc)
        yield sse_frame("error", {"code": 500, "message": "服务器内部异常，请稍后重试"})
    finally:
        db.close()


@router.post("/query", summary="智能流式问答（SSE）")
def query(
    payload: ChatQueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_owned_session(db, payload.session_id, user)
    question = (payload.query or "").strip()
    if not question:
        raise BadRequest("提问内容不能为空")

    return StreamingResponse(
        _event_stream(user.id, session.id, question, payload.enable_rag),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭 Nginx 缓冲，确保增量文本实时抵达浏览器
            "X-Accel-Buffering": "no",
        },
    )
