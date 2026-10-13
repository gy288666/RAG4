"""Durable Phase 2 preparation records; success does not mean index activation."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StoredChunkSet(Base):
    """Content-addressed complete parent/child snapshot, insert-only in the service."""

    __tablename__ = "document_chunk_sets"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    payload_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentIndexJob(Base):
    """Chunk preparation only: pending -> running -> succeeded/failed.

    Each retry uses a new idempotency key. A running job is never reclaimed
    automatically: recovery/leases belong to a later worker slice.
    """

    __tablename__ = "document_index_jobs"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_index_job_request"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(64).with_variant(String(64, collation="utf8mb4_bin"), "mysql")
    )
    kind: Mapped[str] = mapped_column(String(32), default="prepare_chunks")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    source_sha256: Mapped[str] = mapped_column(String(64))
    config_json: Mapped[str] = mapped_column(Text)
    chunk_set_id: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
