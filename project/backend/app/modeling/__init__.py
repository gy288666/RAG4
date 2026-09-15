"""可替换模型运行时。

在线业务只依赖这里定义的 interface；远程 API 与本地微调模型作为 Adapter
接入，训练框架依赖不会泄漏到 RAG 编排代码。
"""

from app.modeling.interfaces import (
    EmbeddingModel,
    ModelDescriptor,
    ModelRuntimeError,
    ModelRuntimeTimeout,
    RankedIndex,
    RerankerModel,
)

__all__ = [
    "EmbeddingModel",
    "ModelDescriptor",
    "ModelRuntimeError",
    "ModelRuntimeTimeout",
    "RankedIndex",
    "RerankerModel",
]
