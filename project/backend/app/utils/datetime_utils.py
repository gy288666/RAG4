"""时间格式化工具：全站统一 ``YYYY-MM-DD HH:MM:SS`` 字符串输出。"""

from __future__ import annotations

from datetime import datetime

FORMAT = "%Y-%m-%d %H:%M:%S"


def fmt(value: datetime | None) -> str | None:
    return value.strftime(FORMAT) if value else None


def now() -> datetime:
    """统一使用服务器本地时间，与 MySQL ``CURRENT_TIMESTAMP`` 保持一致。"""
    return datetime.now()
