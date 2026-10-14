"""Compare existing chunkers using version-independent source evidence spans.

This pilot measures retrieval coverage of annotated anchors, not whether an
answer is correct or a citation supports a claim. AI labels require human review.
PDF pages remain flat parser blocks; no layout or heading extraction is invented.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.adapter import adapt_parse_result
from app.services.chunking_service import split_blocks
from app.services.parser_service import ParseResult, parse


class Label(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Paper(Label):
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")
    pdf_url: str = Field(pattern=r"^https://")
    file_name: str = Field(pattern=r"^[A-Za-z0-9_-]+\.pdf$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: int = Field(strict=True, gt=0)
    license: str
    license_url: str = Field(pattern=r"^https://")


class Evidence(Label):
    document_id: str
    page: int = Field(strict=True, gt=0)
    anchor: str = Field(min_length=3)


class Question(Label):
    id: str = Field(min_length=1)
    category: Literal["fact", "comparison", "multihop", "unanswerable"]
    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def check_answerability(self):
        if (self.category == "unanswerable") != (not self.evidence):
            raise ValueError("Only unanswerable questions may have no gold evidence")
        return self


class Pilot(Label):
    schema_version: Literal["literature-pilot-v1"]
    corpus_version: str = Field(min_length=1)
    annotation_status: Literal["ai_draft", "human_reviewed"]
    papers: tuple[Paper, ...] = Field(min_length=1)
    questions: tuple[Question, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_references(self):
        ids = {p.document_id for p in self.papers}
        if len(ids) != len(self.papers) or len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate document or question ID")
        if len({p.file_name for p in self.papers}) != len(self.papers):
            raise ValueError("Duplicate source file")
        if any(e.document_id not in ids for q in self.questions for e in q.evidence):
            raise ValueError("Unknown evidence document")
        return self


@dataclass(frozen=True)
class Span:
    document_id: str
    page: int
    start: int
    end: int


@dataclass(frozen=True)
class Candidate:
    id: str
    document_id: str
    index: int
    text: str
    spans: tuple[Span, ...]
    parent_id: str | None = None


def load_documents(pilot: Pilot, directory: Path) -> dict[str, ParseResult]:
    documents = {}
    for paper in pilot.papers:
        path = directory / paper.file_name
        if hashlib.sha256(path.read_bytes()).hexdigest() != paper.sha256:
            raise ValueError("Source digest mismatch")
        result = parse(str(path))
        if result.page_count != paper.pages or result.used_ocr:
            raise ValueError("Unexpected page count or OCR; freeze a new corpus revision")
        documents[paper.document_id] = result
    return documents


def locate_evidence(pilot: Pilot, documents: dict[str, ParseResult]) -> dict[str, tuple[Span, ...]]:
    """Require each labelled anchor to occur exactly once on its declared page."""
    located = {}
    for question in pilot.questions:
        spans = []
        for evidence in question.evidence:
            pages = [b for b in documents[evidence.document_id].blocks if b.page == evidence.page]
            if len(pages) != 1:
                raise ValueError(f"Missing evidence page: {question.id}")
            # PDF ligatures expand under NFKC; retain an index back to original
            # characters so the gold interval still matches both chunkers.
            characters, offsets = [], []
            for index, char in enumerate(pages[0].text):
                normalized = unicodedata.normalize("NFKC", char)
                characters.append(normalized)
                offsets.extend([index] * len(normalized))
            pattern = r"\s+".join(re.escape(word) for word in
                                   unicodedata.normalize("NFKC", evidence.anchor).split())
            matches = list(re.finditer(pattern, "".join(characters), re.IGNORECASE))
            if len(matches) != 1:
                raise ValueError(f"Ambiguous or missing evidence anchor: {question.id}")
            match = matches[0]
            spans.append(Span(evidence.document_id, evidence.page,
                              offsets[match.start()], offsets[match.end() - 1] + 1))
        located[question.id] = tuple(spans)
    return located


def make_candidates(documents: dict[str, ParseResult], *, size=600, overlap=60, parent_size=1800):
    """Use the same parsed PDFs and explicit character budget for both chunkers."""
    if size < 100 or not 0 <= overlap < size or parent_size < size:
        raise ValueError("Invalid experiment chunk budgets")
    output = {"rag3": [], "rag4": []}
    for document_id, result in documents.items():
        pages = {b.page: b.text for b in result.blocks}
        if None in pages or len(pages) != len(result.blocks):
            raise ValueError("Pilot requires one parser block per PDF page")
        cursors = {page: 0 for page in pages}
        for chunk in split_blocks(result.blocks, size, overlap):
            start = pages[chunk.page].find(chunk.text, cursors[chunk.page])
            if start < 0:
                raise ValueError("Baseline source alignment failed")
            cursors[chunk.page] = start + 1
            output["rag3"].append(Candidate(f"{document_id}:{chunk.chunk_index}", document_id,
                chunk.chunk_index, chunk.text,
                (Span(document_id, chunk.page, start, start + len(chunk.text)),)))
        document = adapt_parse_result(result, document_id=document_id, file_name=document_id + ".pdf")
        chunk_set = ChunkingEngine().split(document, ChunkingConfig(
            child_max_tokens=size, parent_max_tokens=parent_size))
        if not chunk_set.verify(document):
            raise ValueError("ChunkSet integrity failed")
        for chunk in chunk_set.child_chunks:
            output["rag4"].append(Candidate(chunk.chunk_id, document_id, chunk.chunk_index, chunk.text,
                tuple(Span(document_id, span.page_start, span.char_start, span.char_end)
                      for span in chunk.source_locator.spans), chunk.parent_chunk_id))
    return output


def validate_vectors(vectors, count, dimension):
    if len(vectors) != count or any(len(v) != dimension or
        any(not isinstance(x, (float, int)) or isinstance(x, bool) or not math.isfinite(x) for x in v)
        or not any(x != 0 for x in v) for v in vectors):
        raise ValueError("Embedding shape/value validation failed")


def evidence_metrics(gold: tuple[Span, ...], ranked: list[Candidate], ks=(1, 5, 10)):
    """Source-anchor coverage across the union of hits, independent of chunk IDs.

    A gold span counts only when fully covered by intervals on the same document
    and page. Duplicate/overlapping retrieval hits cannot inflate recall. No
    nDCG is claimed because equivalent chunk-level relevance grades are absent.
    """
    if not gold:
        return {"answerability": "not_evaluated", "metrics": None}
    metrics = {}
    for k in ks:
        if k <= 0:
            raise ValueError("K must be positive")
        found = 0
        for target in gold:
            intervals = sorted((max(s.start, target.start), min(s.end, target.end))
                for chunk in ranked[:k] for s in chunk.spans
                if s.document_id == target.document_id and s.page == target.page
                and s.start < target.end and s.end > target.start)
            cursor = target.start
            for start, end in intervals:
                if start > cursor:
                    break
                cursor = max(cursor, end)
            found += cursor >= target.end
        metrics[str(k)] = {"anchor_span_recall": found / len(gold), "all_evidence_covered": found == len(gold)}
    return {"answerability": "answerable_label", "metrics": metrics}
