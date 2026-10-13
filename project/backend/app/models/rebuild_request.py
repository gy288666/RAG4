"""Atomic user-scoped creation deduplication; keys survive task completion."""
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RebuildRequest(Base):
    __tablename__ = "index_rebuild_requests"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    request_key: Mapped[str] = mapped_column(
        String(64).with_variant(String(64, collation="utf8mb4_bin"), "mysql"), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("user_index_rebuilds.id", ondelete="CASCADE"), unique=True)
