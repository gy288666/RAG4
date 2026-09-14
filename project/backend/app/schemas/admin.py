from __future__ import annotations

from pydantic import BaseModel, Field


class RoleStatusUpdate(BaseModel):
    role: str | None = Field(None, description='可选值："user" / "admin"')
    status: int | None = Field(None, description="可选值：1=启用, 0=禁用")


class LLMConfigIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    aux_model: str | None = Field(
        None, description="辅助任务（问题改写、标题生成）模型，留空复用主模型"
    )


class RerankConfigIn(BaseModel):
    api_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    top_k: int | None = Field(None, ge=1, le=50)


class EmbeddingConfigIn(BaseModel):
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ChunkingConfigIn(BaseModel):
    chunk_size: int | None = Field(None, ge=100, le=4000)
    overlap: int | None = Field(None, ge=0, le=1000)


class RetrievalConfigIn(BaseModel):
    top_n: int | None = Field(None, ge=1, le=100, description="向量检索候选数量 Top-N")
    history_rounds: int | None = Field(None, ge=0, le=20, description="多轮对话携带的历史轮数上限")


class ConfigUpdateRequest(BaseModel):
    """PUT /api/v1/admin/configs 请求体，所有字段均为可选。"""

    llm: LLMConfigIn | None = None
    rerank: RerankConfigIn | None = None
    embedding: EmbeddingConfigIn | None = None
    chunking: ChunkingConfigIn | None = None
    retrieval: RetrievalConfigIn | None = None
