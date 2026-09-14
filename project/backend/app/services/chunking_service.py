"""文档切分服务（PRD 4.2.3）。

切片大小与重叠字符数来自 ``system_configs``，管理员可在后台动态调整，
调整后仅对之后上传的文档生效（不回溯历史切片）。

切分策略：优先在段落 → 句子 → 字符 三级边界处断开，避免把一句话劈成两半。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.parser_service import TextBlock

#: 句子结束标点（中英文）
_SENTENCE_END_RE = re.compile(r"(?<=[。！？!?；;\.\n])")


@dataclass(slots=True)
class Chunk:
    """一个待向量化的文本切片。"""

    text: str
    page: int | None
    chunk_index: int


def _split_sentences(text: str) -> list[str]:
    parts = [p for p in _SENTENCE_END_RE.split(text) if p]
    return parts or [text]


def _split_block(text: str, chunk_size: int, overlap: int) -> list[str]:
    """将单段文本按句子边界聚合成不超过 chunk_size 的片段。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sentences: list[str] = []
    for sentence in _split_sentences(text):
        # 超长句子（如无标点的整段英文）按字符硬切
        while len(sentence) > chunk_size:
            sentences.append(sentence[:chunk_size])
            sentence = sentence[chunk_size:]
        if sentence:
            sentences.append(sentence)

    chunks: list[str] = []
    buffer = ""
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) > chunk_size:
            chunks.append(buffer.strip())
            # 重叠：保留上一片尾部 overlap 个字符，避免跨块信息丢失
            buffer = (buffer[-overlap:] if overlap > 0 else "") + sentence
        else:
            buffer += sentence
    if buffer.strip():
        chunks.append(buffer.strip())
    return [c for c in chunks if c]


def split_blocks(
    blocks: list[TextBlock], chunk_size: int = 600, overlap: int = 60
) -> list[Chunk]:
    """把解析结果切分为全局连续编号（0-based）的切片列表。"""
    chunk_size = max(100, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))

    chunks: list[Chunk] = []
    index = 0
    for block in blocks:
        for piece in _split_block(block.text, chunk_size, overlap):
            chunks.append(Chunk(text=piece, page=block.page, chunk_index=index))
            index += 1
    return chunks
