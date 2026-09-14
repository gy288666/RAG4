"""文本向量化服务（PRD 4.2.3 / 4.3.1）。

通过 OpenAI 兼容的 ``/embeddings`` 接口调用 ``Qwen/Qwen3-Embedding-8B``
（模型名可由管理员在后台修改 [M-2]）。

``DEV_MOCK_AI=true`` 时使用本地确定性哈希向量，便于无外网/无 Key 环境下
跑通完整链路与自动化测试（严禁用于生产）。
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time

import httpx

from app.core.config import settings
from app.models.usage_log import EVENT_EMBEDDING_CALL
from app.services import usage_service
from app.services.config_service import RuntimeConfig

logger = logging.getLogger(__name__)

#: Mock 向量维度（真实 Qwen3-Embedding-8B 为 4096 维，此处仅用于离线联调）
MOCK_DIM = 256
#: 单次请求的最大文本条数，避免超出服务端 payload 限制
BATCH_SIZE = 16
#: 云端 Embedding 在多文档并行入库时容易触发读超时 / 429，串行化并有限重试
_EMBED_LOCK = threading.Lock()
_MAX_RETRIES = 3
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EmbeddingError(RuntimeError):
    """向量化失败。"""


def build_endpoint(base_url: str, path: str) -> str:
    """拼接 OpenAI 兼容端点，自动补齐 ``/v1``。"""
    base = (base_url or "").rstrip("/")
    if not base:
        raise EmbeddingError("尚未配置模型服务 Base URL，请在管理后台完成配置")
    if not base.endswith("/v1") and "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/{path.lstrip('/')}"


# ------------------------------------------------------------
# 离线 Mock 向量
# ------------------------------------------------------------


def _mock_embedding(text: str) -> list[float]:
    """基于字符 n-gram 哈希的确定性向量：相同文本恒等，相似文本余弦相近。"""
    vector = [0.0] * MOCK_DIM
    tokens = [text[i : i + 2] for i in range(max(1, len(text) - 1))] or [text]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % MOCK_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[slot] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


# ------------------------------------------------------------
# 对外接口
# ------------------------------------------------------------


def embed_texts(
    texts: list[str], config: RuntimeConfig, *, user_id: int | None = None
) -> list[list[float]]:
    """批量向量化，返回与输入顺序一致的向量列表。"""
    if not texts:
        return []

    if settings.DEV_MOCK_AI:
        return [_mock_embedding(t) for t in texts]

    if not config.embedding_api_key:
        raise EmbeddingError("尚未配置 Embedding API Key，请联系管理员在后台完成配置")

    endpoint = build_endpoint(config.embedding_base_url, "embeddings")
    vectors: list[list[float]] = []
    started = time.perf_counter()

    try:
        # 文档解析线程池会并发打 Embedding；云端接口在并发下容易读超时。
        # 串行化请求，超时 / 429 / 5xx 时有限重试，避免整篇文档直接 failed。
        with _EMBED_LOCK:
            with httpx.Client(timeout=settings.EMBEDDING_TIMEOUT) as client:
                for offset in range(0, len(texts), BATCH_SIZE):
                    batch = texts[offset : offset + BATCH_SIZE]
                    payload = _post_embeddings(client, endpoint, config, batch)
                    items = sorted(payload.get("data", []), key=lambda x: x.get("index", 0))
                    if len(items) != len(batch):
                        raise EmbeddingError("Embedding 服务返回的向量数量与请求不一致")
                    vectors.extend(item["embedding"] for item in items)
    except httpx.HTTPStatusError as exc:
        usage_service.record(
            event_type=EVENT_EMBEDDING_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=f"HTTP {exc.response.status_code}",
        )
        raise EmbeddingError(
            f"Embedding 服务返回错误（HTTP {exc.response.status_code}），请检查模型名称与 API Key"
        ) from exc
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        usage_service.record(
            event_type=EVENT_EMBEDDING_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=str(exc),
        )
        raise EmbeddingError(f"Embedding 服务调用失败：{exc}") from exc

    usage_service.record(
        event_type=EVENT_EMBEDDING_CALL,
        user_id=user_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=True,
    )
    return vectors


def _post_embeddings(
    client: httpx.Client, endpoint: str, config: RuntimeConfig, batch: list[str]
) -> dict:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {config.embedding_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": config.embedding_model, "input": batch},
            )
            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                logger.warning(
                    "Embedding HTTP %s，%s 秒后重试（%d/%d）",
                    response.status_code,
                    1.5 * (attempt + 1),
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(1.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            last_error = exc
            if attempt >= _MAX_RETRIES - 1:
                raise
            logger.warning(
                "Embedding 超时，%s 秒后重试（%d/%d）",
                1.5 * (attempt + 1),
                attempt + 1,
                _MAX_RETRIES,
            )
            time.sleep(1.5 * (attempt + 1))
    raise last_error or EmbeddingError("Embedding 服务调用失败")


def embed_query(text: str, config: RuntimeConfig, *, user_id: int | None = None) -> list[float]:
    vectors = embed_texts([text], config, user_id=user_id)
    if not vectors:
        raise EmbeddingError("问题向量化失败")
    return vectors[0]
