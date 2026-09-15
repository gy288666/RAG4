"""Embedding 的远程与本地 Adapter。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from app.modeling.interfaces import (
    ModelDescriptor,
    ModelRuntimeError,
    ModelRuntimeTimeout,
)

logger = logging.getLogger(__name__)


class RemoteEmbeddingAdapter:
    """OpenAI 兼容 ``/embeddings`` Adapter。"""

    _lock = threading.Lock()
    _retryable_status = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model_id: str,
        version: str,
        timeout: float,
        batch_size: int = 16,
        max_retries: int = 3,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model_id = model_id
        self._version = version
        self._timeout = timeout
        self._batch_size = batch_size
        self._max_retries = max_retries

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor("embedding", "remote", self._model_id, self._version)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise ModelRuntimeError("尚未配置 Embedding API Key，请联系管理员在后台完成配置")
        vectors: list[list[float]] = []
        try:
            # 多文档后台任务会并发调用。对远程接口串行化并有限重试，避免 429
            # 使整篇文档进入 failed。
            with self._lock:
                with httpx.Client(timeout=self._timeout) as client:
                    for offset in range(0, len(texts), self._batch_size):
                        batch = texts[offset : offset + self._batch_size]
                        payload = self._post(client, batch)
                        items = sorted(payload.get("data", []), key=lambda x: x.get("index", 0))
                        if len(items) != len(batch):
                            raise ModelRuntimeError("Embedding 服务返回的向量数量与请求不一致")
                        vectors.extend(item["embedding"] for item in items)
        except ModelRuntimeError:
            raise
        except httpx.TimeoutException as exc:
            raise ModelRuntimeTimeout("Embedding 服务调用超时") from exc
        except httpx.HTTPStatusError as exc:
            raise ModelRuntimeError(
                f"Embedding 服务返回错误（HTTP {exc.response.status_code}），请检查模型名称与 API Key"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ModelRuntimeError(f"Embedding 服务调用失败：{exc}") from exc
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise ModelRuntimeError("问题向量化失败")
        return vectors[0]

    def _post(self, client: httpx.Client, batch: list[str]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self._model_id, "input": batch},
                )
                if (
                    response.status_code in self._retryable_status
                    and attempt < self._max_retries - 1
                ):
                    delay = 1.5 * (attempt + 1)
                    logger.warning("Embedding HTTP %s，%.1f 秒后重试", response.status_code, delay)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self._max_retries - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise last_error or ModelRuntimeError("Embedding 服务调用失败")


class LocalEmbeddingAdapter:
    """Sentence Transformers 本地模型 Adapter，首次使用时延迟加载。"""

    def __init__(self, *, model_path: str, version: str, device: str | None = None) -> None:
        self._model_path = model_path
        self._version = version
        self._device = device
        self._model = None
        self._lock = threading.Lock()

    @property
    def descriptor(self) -> ModelDescriptor:
        dimension = None
        if self._model is not None:
            dimension = self._model.get_sentence_embedding_dimension()
        return ModelDescriptor("embedding", "local", self._model_path, self._version, dimension)

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise ModelRuntimeError(
                        "本地 Embedding 需要安装 requirements-local-models.txt"
                    ) from exc
                try:
                    self._model = SentenceTransformer(self._model_path, device=self._device)
                except Exception as exc:
                    raise ModelRuntimeError(f"加载本地 Embedding 失败：{exc}") from exc
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            values = self._load().encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return values.tolist()
        except ModelRuntimeError:
            raise
        except Exception as exc:
            raise ModelRuntimeError(f"本地 Embedding 推理失败：{exc}") from exc

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise ModelRuntimeError("问题向量化失败")
        return vectors[0]
