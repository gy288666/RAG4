"""时间有序的业务 ID 生成器。

``DATETIME`` 字段（MySQL 与 SQLite 均然）只精确到秒，同一秒内插入的多条记录
仅靠 ``created_at`` 排序会出现顺序不定的问题——对话消息的「一问一答」顺序因此
可能颠倒。这里让 ID 本身按时间单调递增（纳秒时间戳 + 随机后缀），
排序时使用 ``ORDER BY created_at, id`` 即可得到稳定且正确的时序。
"""

from __future__ import annotations

import os
import threading
import time

_lock = threading.Lock()
_last_ns = 0


def _monotonic_ns() -> int:
    """严格单调递增的纳秒时间戳，避免同一时刻并发生成重复前缀。"""
    global _last_ns
    with _lock:
        value = time.time_ns()
        if value <= _last_ns:
            value = _last_ns + 1
        _last_ns = value
        return value


def generate_id(prefix: str) -> str:
    """生成形如 ``msg_17d1f3a0c8b40000a1b2c3d4`` 的有序 ID。"""
    return f"{prefix}_{_monotonic_ns():016x}{os.urandom(4).hex()}"
