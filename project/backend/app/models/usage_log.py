from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

EVENT_LLM_CALL = "llm_call"
EVENT_RERANK_CALL = "rerank_call"
EVENT_OCR_CALL = "ocr_call"
EVENT_VECTOR_SEARCH = "vector_search"
EVENT_EMBEDDING_CALL = "embedding_call"


class UsageLog(Base):
    """系统运行日志表 usage_logs [I-4]，管理后台监控统计的数据来源。"""

    __tablename__ = "usage_logs"

    # SQLite 仅对 INTEGER 主键启用 rowid 自增，故为其提供变体类型
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_success: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, index=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # v1.2 扩展：关联业务对象 ID（OCR 失败队列需要回溯到具体 doc_id）
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
