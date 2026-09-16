"""RAG4 chunking contracts, independent of parsers, databases and vector stores.

Offsets are Python Unicode character offsets into a ParsedBlock (end exclusive).
Pages are one-based; page_count=0 means unknown. Models are immutable, JSON
serializable snapshots. Content hashes are integrity checks, not signatures.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def content_id(prefix: str, value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return prefix + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SourceInfo(Snapshot):
    """Stable source identity; avoid machine-specific paths for portable IDs."""

    uri: Identifier
    media_type: str | None = None
    used_ocr: bool = False


class TableMetadata(Snapshot):
    table_id: Identifier
    caption: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


class FormulaMetadata(Snapshot):
    formula_id: Identifier
    latex: str | None = None
    label: str | None = None


class ParsedBlock(Snapshot):
    block_id: Identifier
    text: str
    kind: Literal["paragraph", "heading", "table", "formula", "code"] = "paragraph"
    heading_level: Annotated[int, Field(strict=True, ge=1, le=6)] | None = None
    section_path: tuple[Identifier, ...] = ()
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    table: TableMetadata | None = None
    formula: FormulaMetadata | None = None

    @model_validator(mode="after")
    def validate_structure(self):
        if (self.kind == "heading") != (self.heading_level is not None):
            raise ValueError("heading_level is required only for heading blocks")
        if self.kind == "heading" and not self.text.strip():
            raise ValueError("heading text must not be blank")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be provided together")
        if self.page_start is not None and self.page_end < self.page_start:
            raise ValueError("invalid page range")
        return self


class ParsedDocument(Snapshot):
    document_id: Identifier
    file_name: Identifier
    page_count: NonNegativeInt = 0
    blocks: tuple[ParsedBlock, ...] = ()
    source: SourceInfo
    parser_version: Identifier

    @model_validator(mode="after")
    def validate_blocks(self):
        if len({b.block_id for b in self.blocks}) != len(self.blocks):
            raise ValueError("block_id must be unique within a document")
        if self.page_count and any((b.page_end or 0) > self.page_count for b in self.blocks):
            raise ValueError("block page exceeds page_count")
        return self


class ChunkingConfig(Snapshot):
    chunking_version: Identifier = "rag4-structured-v1"
    child_max_tokens: PositiveInt = 256
    parent_max_tokens: PositiveInt = 1024

    @model_validator(mode="after")
    def validate_limits(self):
        if self.child_max_tokens > self.parent_max_tokens:
            raise ValueError("child_max_tokens must not exceed parent_max_tokens")
        return self


class SourceSpan(Snapshot):
    block_id: Identifier
    char_start: NonNegativeInt
    char_end: NonNegativeInt
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.char_end <= self.char_start:
            raise ValueError("source span must be nonempty")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("source pages must be provided together")
        if self.page_start is not None and self.page_end < self.page_start:
            raise ValueError("invalid source page range")
        return self


class SourceLocator(Snapshot):
    source: SourceInfo
    spans: tuple[SourceSpan, ...] = Field(min_length=1)


class DocumentChunk(Snapshot):
    chunk_id: Identifier
    document_id: Identifier
    text: str = Field(min_length=1)
    chunk_index: NonNegativeInt
    chunking_version: Identifier
    title: str | None = None
    section_path: tuple[str, ...] = ()
    parent_chunk_id: str | None = None
    is_parent: bool
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    table_metadata: tuple[TableMetadata, ...] = ()
    formula_metadata: tuple[FormulaMetadata, ...] = ()
    source_locator: SourceLocator
    token_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_structure(self):
        if self.is_parent != (self.parent_chunk_id is None):
            raise ValueError("only children must reference a parent")
        starts = [s.page_start for s in self.source_locator.spans if s.page_start is not None]
        ends = [s.page_end for s in self.source_locator.spans if s.page_end is not None]
        if self.page_start != (min(starts) if starts else None) or self.page_end != (max(ends) if ends else None):
            raise ValueError("chunk page range must match source spans")
        return self

    def expected_id(self, input_id: str) -> str:
        return content_id("chunk_", {"input_id": input_id, **self.model_dump(mode="json", exclude={"chunk_id"})})


class ChunkStats(Snapshot):
    input_blocks: NonNegativeInt
    parent_count: NonNegativeInt
    child_count: NonNegativeInt
    child_tokens: NonNegativeInt
    parent_tokens: NonNegativeInt


class ChunkSet(Snapshot):
    """Complete in-memory result for a future index job; no activation side effects.

    input_id hashes the parsed document, config, engine and token counter identity.
    chunk_set_id additionally hashes the output. Timing belongs in logs so the
    entire serialized result remains reproducible.
    """

    chunk_set_id: Identifier
    input_id: Identifier
    document_id: Identifier
    chunking_version: Identifier
    parser_version: Identifier
    engine_version: Identifier
    tokenizer_id: Identifier
    config: ChunkingConfig
    parent_chunks: tuple[DocumentChunk, ...]
    child_chunks: tuple[DocumentChunk, ...]
    stats: ChunkStats

    def expected_id(self) -> str:
        return content_id("chunkset_", self.model_dump(mode="json", exclude={"chunk_set_id"}))

    def verify(self, document: ParsedDocument | None = None) -> bool:
        """Verify content identity, limits, sequence and parent references.

        Passing the original document additionally verifies input provenance.
        """
        if document is not None:
            expected_input = content_id("input_", {
                "document": document.model_dump(mode="json"), "config": self.config.model_dump(mode="json"),
                "engine": self.engine_version, "tokenizer": self.tokenizer_id,
            })
            if expected_input != self.input_id or self.stats.input_blocks != len(document.blocks):
                return False
        parents = {c.chunk_id: c for c in self.parent_chunks}
        chunks = self.parent_chunks + self.child_chunks
        return (
            self.chunk_set_id == self.expected_id()
            and self.chunking_version == self.config.chunking_version
            and len({c.chunk_id for c in chunks}) == len(chunks)
            and all(c.chunk_id == c.expected_id(self.input_id) for c in chunks)
            and all(c.document_id == self.document_id and c.chunking_version == self.chunking_version for c in chunks)
            and all(c.is_parent and c.parent_chunk_id is None and c.token_count <= self.config.parent_max_tokens for c in self.parent_chunks)
            and all(not c.is_parent and c.parent_chunk_id in parents and c.token_count <= self.config.child_max_tokens for c in self.child_chunks)
            and all(c.section_path == parents[c.parent_chunk_id].section_path and c.text in parents[c.parent_chunk_id].text for c in self.child_chunks)
            and [c.chunk_index for c in self.parent_chunks] == list(range(len(self.parent_chunks)))
            and [c.chunk_index for c in self.child_chunks] == list(range(len(self.child_chunks)))
            and self.stats.parent_count == len(self.parent_chunks)
            and self.stats.child_count == len(self.child_chunks)
            and self.stats.child_tokens == sum(c.token_count for c in self.child_chunks)
            and self.stats.parent_tokens == sum(c.token_count for c in self.parent_chunks)
        )
