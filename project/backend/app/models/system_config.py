from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemConfig(Base):
    """系统全局动态配置表 system_configs。

    [S-1] API Key 类字段以 AES-256 密文形式存储，任何响应均不返回明文。
    """

    __tablename__ = "system_configs"

    config_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    config_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
