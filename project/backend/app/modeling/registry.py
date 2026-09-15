"""按运行配置解析模型 Adapter，并缓存重量级本地模型。"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.modeling.adapters import (
    LocalEmbeddingAdapter,
    LocalRerankerAdapter,
    RemoteEmbeddingAdapter,
    RemoteRerankerAdapter,
)
from app.modeling.interfaces import EmbeddingModel, ModelRuntimeError, RerankerModel


def _endpoint(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if not base:
        raise ModelRuntimeError("尚未配置模型服务 Base URL，请在管理后台完成配置")
    if not base.endswith("/v1") and "/v1" not in base:
        base = f"{base}/v1"
    return f"{base}/{path.lstrip('/')}"


@lru_cache(maxsize=4)
def _local_embedding(model_path: str, version: str) -> LocalEmbeddingAdapter:
    return LocalEmbeddingAdapter(model_path=model_path, version=version)


@lru_cache(maxsize=4)
def _local_reranker(model_path: str, version: str) -> LocalRerankerAdapter:
    return LocalRerankerAdapter(model_path=model_path, version=version)


def resolve_embedding_model(config) -> EmbeddingModel:
    provider = getattr(config, "embedding_provider", "remote")
    version = getattr(config, "embedding_version", "baseline") or "baseline"
    if provider == "local":
        model_path = getattr(config, "embedding_local_path", "") or config.embedding_model
        if not model_path:
            raise ModelRuntimeError("本地 Embedding 未配置模型目录或模型名称")
        return _local_embedding(model_path, version)
    return RemoteEmbeddingAdapter(
        endpoint=_endpoint(config.embedding_base_url, "embeddings"),
        api_key=config.embedding_api_key,
        model_id=config.embedding_model,
        version=version,
        timeout=settings.EMBEDDING_TIMEOUT,
    )


def resolve_reranker_model(config) -> RerankerModel:
    provider = getattr(config, "rerank_provider", "remote")
    version = getattr(config, "rerank_version", "baseline") or "baseline"
    if provider == "local":
        model_path = getattr(config, "rerank_local_path", "") or config.rerank_model
        if not model_path:
            raise ModelRuntimeError("本地 Reranker 未配置模型目录或模型名称")
        return _local_reranker(model_path, version)
    return RemoteRerankerAdapter(
        endpoint=config.rerank_api_url,
        api_key=config.rerank_api_key,
        model_id=config.rerank_model,
        version=version,
        timeout=settings.RERANK_TIMEOUT,
    )


def clear_model_cache() -> None:
    """配置切换或测试结束后释放 Adapter 引用。"""
    _local_embedding.cache_clear()
    _local_reranker.cache_clear()
