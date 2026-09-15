"""Reranker 的远程与本地 Adapter。"""

from __future__ import annotations

import threading
from typing import Any

import httpx

from app.modeling.interfaces import (
    ModelDescriptor,
    ModelRuntimeError,
    ModelRuntimeTimeout,
    RankedIndex,
)


def parse_rerank_results(payload: dict[str, Any]) -> list[RankedIndex]:
    """兼容 Cohere 与阿里云百炼响应。"""
    items = payload.get("results")
    if items is None:
        items = (payload.get("output") or {}).get("results")
    if items is None:
        return []
    parsed: list[RankedIndex] = []
    for item in items:
        if not isinstance(item, dict) or item.get("index") is None:
            continue
        try:
            score = item.get("relevance_score", item.get("score", 0.0))
            parsed.append(RankedIndex(int(item["index"]), float(score)))
        except (TypeError, ValueError):
            continue
    return parsed


class RemoteRerankerAdapter:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model_id: str,
        version: str,
        timeout: float,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._model_id = model_id
        self._version = version
        self._timeout = timeout

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor("reranker", "remote", self._model_id, self._version)

    def rank(self, query: str, passages: list[str], top_k: int) -> list[RankedIndex]:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model_id,
                        "query": query,
                        "documents": passages,
                        "top_n": top_k,
                    },
                )
                response.raise_for_status()
                return parse_rerank_results(response.json())
        except httpx.TimeoutException as exc:
            raise ModelRuntimeTimeout("Rerank 调用超时") from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise ModelRuntimeError(f"Rerank 调用失败：{exc}") from exc


class LocalRerankerAdapter:
    """Sentence Transformers CrossEncoder Adapter，首次使用时延迟加载。"""

    def __init__(self, *, model_path: str, version: str, device: str | None = None) -> None:
        self._model_path = model_path
        self._version = version
        self._device = device
        self._model = None
        self._lock = threading.Lock()

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor("reranker", "local", self._model_path, self._version)

    def _load(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise ModelRuntimeError(
                        "本地 Reranker 需要安装 requirements-local-models.txt"
                    ) from exc
                try:
                    self._model = CrossEncoder(self._model_path, device=self._device)
                except Exception as exc:
                    raise ModelRuntimeError(f"加载本地 Reranker 失败：{exc}") from exc
        return self._model

    def rank(self, query: str, passages: list[str], top_k: int) -> list[RankedIndex]:
        if not passages:
            return []
        try:
            scores = self._load().predict([(query, passage) for passage in passages])
        except ModelRuntimeError:
            raise
        except Exception as exc:
            raise ModelRuntimeError(f"本地 Reranker 推理失败：{exc}") from exc
        ranked = [RankedIndex(index, float(score)) for index, score in enumerate(scores)]
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]
