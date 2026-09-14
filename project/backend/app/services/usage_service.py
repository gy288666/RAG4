"""运行日志记录服务 [I-4]。

所有外部调用（LLM / Rerank / OCR / 向量检索）均在此登记耗时、Token 消耗与
成败结果，作为管理后台 ``GET /api/v1/admin/stats`` 的数据来源。
日志写入失败绝不影响主流程。
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.database import session_scope
from app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)


def record(
    *,
    event_type: str,
    user_id: int | None = None,
    tokens_used: int = 0,
    duration_ms: int = 0,
    is_success: bool = True,
    error_message: str | None = None,
    ref_id: str | None = None,
    db: Session | None = None,
) -> None:
    log = UsageLog(
        user_id=user_id,
        event_type=event_type,
        tokens_used=int(tokens_used or 0),
        duration_ms=int(duration_ms or 0),
        is_success=1 if is_success else 0,
        error_message=(error_message or None) and str(error_message)[:512],
        ref_id=ref_id,
    )
    try:
        if db is not None:
            db.add(log)
            db.commit()
        else:
            with session_scope() as scoped:
                scoped.add(log)
    except Exception:  # pragma: no cover - 监控日志不可影响主流程
        logger.warning("写入 usage_logs 失败: event=%s", event_type, exc_info=True)


@contextmanager
def track(event_type: str, *, user_id: int | None = None, ref_id: str | None = None):
    """上下文管理器：自动统计耗时与成败。

    用法::

        with track("llm_call", user_id=1) as usage:
            ...
            usage["tokens_used"] = 128
    """
    started = time.perf_counter()
    state: dict = {"tokens_used": 0}
    try:
        yield state
    except Exception as exc:
        record(
            event_type=event_type,
            user_id=user_id,
            ref_id=ref_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=f"{type(exc).__name__}: {exc}",
            tokens_used=int(state.get("tokens_used", 0)),
        )
        raise
    else:
        record(
            event_type=event_type,
            user_id=user_id,
            ref_id=ref_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=True,
            tokens_used=int(state.get("tokens_used", 0)),
        )
