"""Embedding 门面：记录用量并把调用委托给可替换模型 Adapter。"""

from __future__ import annotations

import hashlib
import math
import time

from app.core.config import settings
from app.modeling import ModelRuntimeError
from app.modeling import registry as model_registry
from app.models.usage_log import EVENT_EMBEDDING_CALL
from app.services import usage_service
from app.services.config_service import RuntimeConfig

MOCK_DIM = 256


class EmbeddingError(RuntimeError):
    """向量化失败。"""


def build_endpoint(base_url: str, path: str) -> str:
    """兼容旧调用者的 OpenAI 端点拼接函数。"""
    base = (base_url or "").rstrip("/")
    if not base:
        raise EmbeddingError("尚未配置模型服务 Base URL，请在管理后台完成配置")
    if not base.endswith("/v1") and "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/{path.lstrip('/')}"


def _mock_embedding(text: str) -> list[float]:
    vector = [0.0] * MOCK_DIM
    tokens = [text[i : i + 2] for i in range(max(1, len(text) - 1))] or [text]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % MOCK_DIM
        vector[slot] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def embed_texts(
    texts: list[str], config: RuntimeConfig, *, user_id: int | None = None
) -> list[list[float]]:
    """批量向量化；远程与本地微调模型共用同一 interface。"""
    if not texts:
        return []
    if settings.DEV_MOCK_AI:
        return [_mock_embedding(text) for text in texts]

    started = time.perf_counter()
    try:
        model = model_registry.resolve_embedding_model(config)
        vectors = model.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ModelRuntimeError("Embedding 返回的向量数量与文本数量不一致")
    except ModelRuntimeError as exc:
        _record(user_id, started, False, str(exc))
        raise EmbeddingError(str(exc)) from exc

    _record(user_id, started, True)
    return vectors


def embed_query(text: str, config: RuntimeConfig, *, user_id: int | None = None) -> list[float]:
    if settings.DEV_MOCK_AI:
        return _mock_embedding(text)

    started = time.perf_counter()
    try:
        vector = model_registry.resolve_embedding_model(config).embed_query(text)
    except ModelRuntimeError as exc:
        _record(user_id, started, False, str(exc))
        raise EmbeddingError(str(exc)) from exc
    _record(user_id, started, True)
    return vector


def _record(
    user_id: int | None,
    started: float,
    is_success: bool,
    error_message: str | None = None,
) -> None:
    usage_service.record(
        event_type=EVENT_EMBEDDING_CALL,
        user_id=user_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=is_success,
        error_message=error_message,
    )
