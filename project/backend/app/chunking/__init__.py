"""Public RAG4 chunking API. The RAG3 chunking_service remains independent."""

from .engine import CharacterTokenCounter, ChunkingEngine, TokenCounter, TokenizerTokenCounter
from .models import (
    ChunkingConfig, ChunkSet, ChunkStats, DocumentChunk, FormulaMetadata,
    ParsedBlock, ParsedDocument, SourceInfo, SourceLocator, SourceSpan, TableMetadata,
)

__all__ = [
    "CharacterTokenCounter", "ChunkingEngine", "TokenCounter", "TokenizerTokenCounter",
    "ChunkingConfig", "ChunkSet", "ChunkStats", "DocumentChunk", "FormulaMetadata",
    "ParsedBlock", "ParsedDocument", "SourceInfo", "SourceLocator", "SourceSpan", "TableMetadata",
]
