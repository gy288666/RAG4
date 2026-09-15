"""模型 Adapter 实现。"""

from app.modeling.adapters.embedding import LocalEmbeddingAdapter, RemoteEmbeddingAdapter
from app.modeling.adapters.reranker import LocalRerankerAdapter, RemoteRerankerAdapter

__all__ = [
    "LocalEmbeddingAdapter",
    "RemoteEmbeddingAdapter",
    "LocalRerankerAdapter",
    "RemoteRerankerAdapter",
]
