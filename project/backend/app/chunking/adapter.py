"""Compatibility bridge: keep legacy ParseResult/TextBlock usable unchanged.

Legacy plain text cannot recover layout already discarded by a parser. The
optional structured_blocks side channel takes precedence; otherwise each old
block becomes a paragraph with its original page. No heading guesses are made.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import ParsedBlock, ParsedDocument, SourceInfo

if TYPE_CHECKING:
    from app.services.parser_service import ParseResult


def adapt_parse_result(
    result: ParseResult, *, document_id: str, file_name: str,
    source: SourceInfo | None = None,
) -> ParsedDocument:
    from app.services.parser_service import ParseResult

    if not isinstance(result, ParseResult):
        raise TypeError("result must be a ParseResult")
    blocks = result.structured_blocks
    if blocks is None:
        blocks = tuple(
            ParsedBlock(block_id=f"block-{index}", text=block.text, page_start=block.page, page_end=block.page)
            for index, block in enumerate(result.blocks)
        )
    return ParsedDocument(
        document_id=document_id, file_name=file_name, page_count=result.page_count,
        blocks=blocks, parser_version=result.parser_version,
        source=source or SourceInfo(uri=f"document:{document_id}", used_ocr=result.used_ocr),
    )


def markdown_blocks(raw: str) -> tuple[ParsedBlock, ...]:
    """Preserve ATX/setext headings and fenced code before legacy flattening.

    This is deliberately a small compatibility adapter, not a full Markdown AST.
    Tables and formula syntax remain text; richer parsers can supply typed blocks.
    """
    from app.services.parser_service import _markdown_to_text, clean_text

    blocks: list[ParsedBlock] = []
    pending: list[str] = []
    fence: str | None = None

    def emit(text: str, kind="paragraph", level=None):
        text = text if kind == "code" else clean_text(_markdown_to_text(text))
        if text.strip():
            blocks.append(ParsedBlock(block_id=f"block-{len(blocks)}", text=text, kind=kind, heading_level=level))

    def flush(kind="paragraph"):
        emit("\n".join(pending), kind)
        pending.clear()

    for line in raw.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            if marker and set(line.strip()) == {fence[0]} and len(marker[1]) >= len(fence):
                flush("code")
                fence = None
            else:
                pending.append(line)
            continue
        if marker:
            flush()
            fence = marker[1]
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        underline = re.match(r"^\s{0,3}(=+|-+)\s*$", line)
        if heading:
            flush()
            emit(re.sub(r"\s+#+\s*$", "", heading[2]), "heading", len(heading[1]))
        elif underline and len(pending) == 1 and pending[0].strip():
            emit(pending.pop(), "heading", 1 if underline[1][0] == "=" else 2)
        elif not line.strip():
            flush()
        else:
            pending.append(line)
    flush("code" if fence is not None else "paragraph")
    return tuple(blocks)
