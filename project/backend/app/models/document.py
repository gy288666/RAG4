from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 状态机：pending → parsing → vectorizing → ready / failed
STATUS_PENDING = "pending"
STATUS_PARSING = "parsing"
STATUS_VECTORIZING = "vectorizing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

ALL_STATUSES = (
    STATUS_PENDING,
    STATUS_PARSING,
    STATUS_VECTORIZING,
    STATUS_READY,
    STATUS_FAILED,
)

# 前端展示用的中文状态文案（PRD 4.2.4）
STATUS_LABELS = {
    STATUS_PENDING: "排队中",
    STATUS_PARSING: "解析中",
    STATUS_VECTORIZING: "向量化中",
    STATUS_READY: "已就绪",
    STATUS_FAILED: "失败",
}


class Document(Base):
    """文档元数据与解析状态表 documents。"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False, index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # [I-1] BIGINT 支持大文件扩展
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    local_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=STATUS_PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # [M-1] 状态最后更新时间，前端轮询判断解析是否卡滞
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), index=True
    )
