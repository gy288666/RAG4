"""Deterministic section -> paragraph -> sentence -> character chunking.

No network/tokenizer downloads. An injected counter must be deterministic and
have a revisioned identity. Without one, Unicode characters are the explicit
budget unit (an estimate, not a guarantee for a particular model tokenizer).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

from .models import (
    ChunkingConfig, ChunkSet, ChunkStats, DocumentChunk, ParsedBlock,
    ParsedDocument, SourceLocator, SourceSpan, content_id,
)

logger = logging.getLogger(__name__)
ENGINE_VERSION = "structure-boundaries-v1"


class TokenCounter(Protocol):
    identity: str

    def count(self, text: str) -> int: ...


class CharacterTokenCounter:
    identity = "unicode-codepoint-v1"

    def count(self, text: str) -> int:
        return len(text)


class TokenizerTokenCounter:
    """Adapter for an already-loaded HF-compatible tokenizer; never downloads.

    identity must include the tokenizer revision. Special tokens are excluded;
    callers reserve model-specific special-token overhead in their budgets.
    A runtime tokenizer failure aborts the split instead of mixing counters.
    """

    def __init__(self, tokenizer, *, identity: str):
        if not identity.strip():
            raise ValueError("tokenizer identity must not be blank")
        self.tokenizer = tokenizer
        self.identity = identity

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))


@dataclass(frozen=True)
class _Region:
    start: int
    end: int
    block: ParsedBlock


class ChunkingEngine:
    def __init__(self, token_counter: TokenCounter | None = None):
        self.counter = token_counter if token_counter is not None else CharacterTokenCounter()
        if not isinstance(self.counter.identity, str) or not self.counter.identity.strip():
            raise ValueError("token counter identity must not be blank")

    def _count(self, text: str) -> int:
        count = self.counter.count(text)
        if type(count) is not int or count < 0:
            raise ValueError("token counter must return a nonnegative integer")
        return count

    def _ranges(self, text: str, limit: int, *, preserve_whitespace: bool = False):
        """Yield exact non-overlapping slices; never decode sliced token IDs.

        Prefix token counts need not be monotone (BPE merges). Binary search
        finds a fitting prefix, not necessarily the longest; every selected
        boundary is counted again. If binary search finds no prefix, an exhaustive
        prefix search handles non-monotone counts before declaring no fit.
        """
        start = 0
        while start < len(text):
            if not preserve_whitespace and text[start].isspace():
                start += 1
                continue
            if type(self.counter) is CharacterTokenCounter:
                best = min(start + limit, len(text))
            elif self._count(text[start:]) <= limit:
                best = len(text)
            else:
                best = start
            low, high = start + 1, len(text) if best == start else start
            while low <= high:
                mid = (low + high) // 2
                if self._count(text[start:mid]) <= limit:
                    best, low = mid, mid + 1
                else:
                    high = mid - 1
            if best == start:
                best = next((end for end in range(start + 1, len(text) + 1)
                             if self._count(text[start:end]) <= limit), start)
                if best == start:
                    raise ValueError("token budget cannot fit a source character")
            end = best
            if best < len(text):
                prefix = text[start:best]
                for pattern in (r"\n\s*\n", r"(?<=[。！？!?；;.])\s*", r"\s+"):
                    candidates = [start + m.end() for m in re.finditer(pattern, prefix)]
                    fit = next((c for c in reversed(candidates) if c > start and self._count(text[start:c] if preserve_whitespace else text[start:c].rstrip()) <= limit), None)
                    if fit is not None:
                        end = fit
                        break
            # Trimming can alter BPE merges, so validate the actual output.
            while not preserve_whitespace and end > start and text[end - 1].isspace():
                end -= 1
            while end > start and self._count(text[start:end]) > limit:
                end -= 1
            if end <= start:
                raise ValueError("token budget cannot fit a source character")
            yield start, end
            start = end

    def split(self, document: ParsedDocument, config: ChunkingConfig | None = None) -> ChunkSet:
        if not isinstance(document, ParsedDocument):
            raise TypeError("document must be a ParsedDocument")
        config = config or ChunkingConfig()
        started = time.perf_counter()
        try:
            result = self._split(document, config)
        except Exception:
            logger.exception("chunking failed document=%s version=%s tokenizer=%s elapsed_ms=%.3f", document.document_id, config.chunking_version, self.counter.identity, (time.perf_counter() - started) * 1000)
            raise
        logger.info("chunking complete document=%s version=%s tokenizer=%s chunk_set=%s parents=%d children=%d elapsed_ms=%.3f", document.document_id, config.chunking_version, self.counter.identity, result.chunk_set_id, result.stats.parent_count, result.stats.child_count, (time.perf_counter() - started) * 1000)
        return result

    def _split(self, document: ParsedDocument, config: ChunkingConfig) -> ChunkSet:
        input_id = content_id("input_", {
            "document": document.model_dump(mode="json"), "config": config.model_dump(mode="json"),
            "engine": ENGINE_VERSION, "tokenizer": self.counter.identity,
        })
        parents: list[DocumentChunk] = []
        children: list[DocumentChunk] = []
        headings: list[tuple[int, str]] = []
        groups: list[tuple[tuple[str, ...], list[ParsedBlock]]] = []
        for block in document.blocks:
            if not block.text.strip():
                continue
            if block.kind == "heading":
                headings = [(level, title) for level, title in headings if level < block.heading_level]
                headings.append((block.heading_level, block.text.strip()))
            path = block.section_path or tuple(title for _, title in headings)
            # Tables/formulas/code get their own parents, never mixed with prose.
            isolated = block.kind in {"table", "formula", "code"}
            if (not groups or groups[-1][0] != path or block.kind == "heading" or isolated
                    or groups[-1][1][-1].kind in {"table", "formula", "code"}):
                groups.append((path, []))
            groups[-1][1].append(block)

        for path, blocks in groups:
            regions: list[_Region] = []
            position = 0
            for block in blocks:
                regions.append(_Region(position, position + len(block.text), block))
                position += len(block.text) + 2
            text = "\n\n".join(b.text for b in blocks)

            def make_chunk(start: int, end: int, *, parent: DocumentChunk | None) -> DocumentChunk:
                spans, tables, formulas = [], [], []
                for region in regions:
                    left, right = max(start, region.start), min(end, region.end)
                    if left >= right:
                        continue
                    block = region.block
                    spans.append(SourceSpan(block_id=block.block_id, char_start=left - region.start, char_end=right - region.start, page_start=block.page_start, page_end=block.page_end))
                    if block.table is not None and block.table not in tables:
                        tables.append(block.table)
                    if block.formula is not None and block.formula not in formulas:
                        formulas.append(block.formula)
                pages_start = [s.page_start for s in spans if s.page_start is not None]
                pages_end = [s.page_end for s in spans if s.page_end is not None]
                chunk = DocumentChunk(
                    chunk_id="pending", document_id=document.document_id, text=text[start:end],
                    chunk_index=len(parents) if parent is None else len(children),
                    chunking_version=config.chunking_version, title=path[-1] if path else None,
                    section_path=path, parent_chunk_id=parent.chunk_id if parent else None,
                    is_parent=parent is None, page_start=min(pages_start) if pages_start else None,
                    page_end=max(pages_end) if pages_end else None, table_metadata=tuple(tables),
                    formula_metadata=tuple(formulas), source_locator=SourceLocator(source=document.source, spans=tuple(spans)),
                    token_count=self._count(text[start:end]),
                )
                return chunk.model_copy(update={"chunk_id": chunk.expected_id(input_id)})

            preserve = blocks[0].kind == "code"
            for start, end in self._ranges(text, config.parent_max_tokens, preserve_whitespace=preserve):
                parent = make_chunk(start, end, parent=None)
                parents.append(parent)
                for child_start, child_end in self._ranges(parent.text, config.child_max_tokens, preserve_whitespace=preserve):
                    children.append(make_chunk(start + child_start, start + child_end, parent=parent))
        result = ChunkSet(
            chunk_set_id="pending", input_id=input_id, document_id=document.document_id,
            chunking_version=config.chunking_version, parser_version=document.parser_version,
            engine_version=ENGINE_VERSION, tokenizer_id=self.counter.identity, config=config,
            parent_chunks=tuple(parents), child_chunks=tuple(children),
            stats=ChunkStats(input_blocks=len(document.blocks), parent_count=len(parents), child_count=len(children),
                             parent_tokens=sum(c.token_count for c in parents), child_tokens=sum(c.token_count for c in children)),
        )
        return result.model_copy(update={"chunk_set_id": result.expected_id()})
