"""One durable successor per interrupted batch; original execution stays fenced."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RebuildRecovery(Base):
    __tablename__ = "index_rebuild_recoveries"
    source_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_index_rebuilds.id", ondelete="CASCADE"), primary_key=True)
    target_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_index_rebuilds.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
