from __future__ import annotations

from pydantic import BaseModel, Field


class SessionTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="新的会话标题")


class ChatQueryRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    query: str = Field(..., min_length=1, max_length=4000)
    # [S-4] false 时跳过向量检索与 Rerank，仅做纯模型对话
    enable_rag: bool = True


class Citation(BaseModel):
    """引用溯源条目 [I-3]。

    PDF 文档 ``page`` 有值；TXT/Markdown 为 null，前端改用 ``chunk_index`` 展示
    “第 N 个片段”。
    """

    index: int
    doc_id: str | None = None
    doc_name: str
    page: int | None = None
    chunk_index: int = 0
    snippet: str = ""
