from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# MEDIUMTEXT（16MB）适配长篇 LLM 回答；SQLite 等其他方言回退为 TEXT
LongText = Text().with_variant(MEDIUMTEXT(), "mysql")


class ChatSession(Base):
    """问答对话会话表 chat_sessions。"""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新对话")
    is_deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), index=True
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class ChatMessage(Base):
    """对话消息记录表 chat_messages（含引用溯源 JSON）。"""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(LongText, nullable=False)
    # enable_rag=false 时为 NULL [S-4]
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
