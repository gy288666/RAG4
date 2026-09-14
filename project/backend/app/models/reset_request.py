from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PasswordResetRequest(Base):
    """密码重置申请记录表（流程 B：用户提交 → 管理员后台处理）。"""

    __tablename__ = "password_reset_requests"
    __table_args__ = (
        Index("idx_reset_email_handled", "email", "is_handled"),
        Index("idx_reset_last_request", "last_request_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    is_handled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # [M-4] 最近一次提交时间，用于应用层 10 分钟频率限制
    last_request_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
