"""Research task checkpoints, separate from chat and index publication."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResearchTaskRecord(Base):
    __tablename__ = "research_tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
