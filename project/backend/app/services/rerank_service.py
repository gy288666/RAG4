"""云端 Rerank 精排服务（PRD 4.3.1）。

兼容 Cohere Rerank 与阿里云百炼 Rerank 两种主流响应结构。

[M-6] 超时（默认 > 3s）或调用失败时**不中断问答**：直接返回向量检索的
Top-K 结果，并通过 ``warnings=["rerank_timeout"]`` 告知前端。
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings
from app.models.usage_log import EVENT_RERANK_CALL
from app.services import usage_service
from app.services.config_service import RuntimeConfig
from app.services.vector_store import RetrievedChunk

logger = logging.getLogger(__name__)

WARNING_RERANK_TIMEOUT = "rerank_timeout"


def _parse_results(payload: dict) -> list[tuple[int, float]]:
    """从不同厂商的响应中解析出 ``[(index, score), ...]``。"""
    # Cohere: {"results": [{"index": 0, "relevance_score": 0.98}, ...]}
    items = payload.get("results")
    # 阿里云百炼: {"output": {"results": [...]}}
    if items is None:
        items = (payload.get("output") or {}).get("results")
    if items is None:
        return []

    parsed: list[tuple[int, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if index is None:
            continue
        score = item.get("relevance_score", item.get("score", 0.0))
        try:
            parsed.append((int(index), float(score)))
        except (TypeError, ValueError):
            continue
    return parsed


def rerank(
    query: str,
    candidates: list[RetrievedChunk],
    config: RuntimeConfig,
    *,
    user_id: int | None = None,
) -> tuple[list[RetrievedChunk], list[str]]:
    """精排候选片段，返回 ``(Top-K 片段, 警告列表)``。

    任何异常都被吞掉并降级为向量检索原始顺序，保证 SSE 连接不中断。
    """
    top_k = max(1, config.rerank_top_k)
    if not candidates:
        return [], []

    # 未配置 Rerank 服务或处于离线 Mock 模式 → 直接截断向量检索结果
    if settings.DEV_MOCK_AI or not config.rerank_api_url or not config.rerank_api_key:
        return candidates[:top_k], []

    started = time.perf_counter()
    documents = [c.text for c in candidates]

    try:
        with httpx.Client(timeout=settings.RERANK_TIMEOUT) as client:
            response = client.post(
                config.rerank_api_url,
                headers={
                    "Authorization": f"Bearer {config.rerank_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    # 模型名各服务商取值不同（Cohere: rerank-multilingual-v3.0；
                    # 硅基流动 / 阿里云百炼: BAAI/bge-reranker-v2-m3 等），由后台配置
                    "model": config.rerank_model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                },
            )
            response.raise_for_status()
            results = _parse_results(response.json())
    except httpx.TimeoutException:
        usage_service.record(
            event_type=EVENT_RERANK_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message="Rerank API 调用超时（> 3s），已降级",
        )
        logger.warning("Rerank 超时，降级为向量检索 Top-K")
        return candidates[:top_k], [WARNING_RERANK_TIMEOUT]
    except (httpx.HTTPError, ValueError) as exc:
        usage_service.record(
            event_type=EVENT_RERANK_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=str(exc),
        )
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
    for index, score in sorted(results, key=lambda x: x[1], reverse=True)[:top_k]:
        if 0 <= index < len(candidates):
            chunk = candidates[index]
            chunk.score = score
            ordered.append(chunk)
    return (ordered or candidates[:top_k]), []
