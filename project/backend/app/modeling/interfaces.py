"""Embedding 与 Reranker 的稳定 interface。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ModelRuntimeError(RuntimeError):
    """模型 Adapter 无法完成请求。"""


class ModelRuntimeTimeout(ModelRuntimeError):
    """模型 Adapter 超时。"""


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """可记录、可比较的模型身份。"""

    task_type: str
    provider: str
    model_id: str
    version: str
    dimension: int | None = None


@dataclass(frozen=True, slots=True)
class RankedIndex:
    """Reranker 输出的候选位置与相关性分数。"""

    index: int
    score: float


@runtime_checkable
class EmbeddingModel(Protocol):
    """文档与查询必须处于同一向量空间。"""

    @property
    def descriptor(self) -> ModelDescriptor: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class RerankerModel(Protocol):
    """对已有候选排序；不得自行扩大检索范围。"""

    @property
    def descriptor(self) -> ModelDescriptor: ...

    def rank(self, query: str, passages: list[str], top_k: int) -> list[RankedIndex]: ...
