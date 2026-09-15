"""Rerank 门面：统一远程基线和本地微调模型，并保留降级语义。"""

from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.modeling import ModelRuntimeError, ModelRuntimeTimeout
from app.modeling import registry as model_registry
from app.modeling.adapters.reranker import parse_rerank_results
from app.models.usage_log import EVENT_RERANK_CALL
from app.services import usage_service
from app.services.config_service import RuntimeConfig
from app.services.vector_store import RetrievedChunk

logger = logging.getLogger(__name__)
WARNING_RERANK_TIMEOUT = "rerank_timeout"


def _parse_results(payload: dict) -> list[tuple[int, float]]:
    """保留 RAG3 测试与调用兼容性。"""
    return [(item.index, item.score) for item in parse_rerank_results(payload)]


def rerank(
    query: str,
    candidates: list[RetrievedChunk],
    config: RuntimeConfig,
    *,
    user_id: int | None = None,
) -> tuple[list[RetrievedChunk], list[str]]:
    """精排候选；Adapter 失败时退回原向量顺序。"""
    top_k = max(1, config.rerank_top_k)
    if not candidates:
        return [], []

    provider = getattr(config, "rerank_provider", "remote")
    if settings.DEV_MOCK_AI:
        return candidates[:top_k], []
    if provider == "remote" and (not config.rerank_api_url or not config.rerank_api_key):
        return candidates[:top_k], []

    started = time.perf_counter()
    try:
        model = model_registry.resolve_reranker_model(config)
        results = model.rank(query, [item.text for item in candidates], top_k)
    except ModelRuntimeTimeout:
        _record_failure(user_id, started, "Rerank 超时，已降级")
        return candidates[:top_k], [WARNING_RERANK_TIMEOUT]
    except ModelRuntimeError as exc:
        _record_failure(user_id, started, str(exc))
        logger.warning("Rerank 调用失败（%s），降级为向量检索 Top-K", exc)
        return candidates[:top_k], [WARNING_RERANK_TIMEOUT]

    usage_service.record(
        event_type=EVENT_RERANK_CALL,
        user_id=user_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=True,
    )
    if not results:
        return candidates[:top_k], [WARNING_RERANK_TIMEOUT]

    ordered: list[RetrievedChunk] = []
    version = getattr(config, "rerank_version", "baseline")
    for result in results:
        if 0 <= result.index < len(candidates):
            chunk = candidates[result.index]
            chunk.score = result.score
            chunk.extra["reranker_model_version"] = version
            ordered.append(chunk)
    return (ordered or candidates[:top_k]), []


def _record_failure(user_id: int | None, started: float, message: str) -> None:
    usage_service.record(
        event_type=EVENT_RERANK_CALL,
        user_id=user_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=False,
        error_message=message,
    )
