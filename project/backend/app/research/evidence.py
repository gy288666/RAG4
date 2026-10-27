"""Version-bound evidence selection with a hard Unicode character budget.

No mutable active pointer is consulted here. Callers supply an owned, verified
corpus and a retriever bound to the same snapshot. Optional compact windows
carry explicit original-parent offsets; citations never use local offsets.
"""
from __future__ import annotations

from collections import defaultdict
import math
import re
from time import perf_counter
from typing import Protocol, Literal

from pydantic import Field, model_validator, model_serializer

from app.chunking.models import ChunkSet, DocumentChunk, Identifier, Snapshot, content_id


class RetrievalOptions(Snapshot):
    document_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=5)
    top_k: int = Field(default=10, strict=True, ge=1, le=20)
    max_items: int = Field(default=10, strict=True, ge=1, le=20)
    max_context_chars: int = Field(default=6000, strict=True, ge=1, le=40000)
    expand_parents: bool = True
    include_graph: bool = True
    context_policy: Literal["parent-floor-v2", "local-window-v3"] = "parent-floor-v2"

    @model_serializer(mode="wrap")
    def preserve_historical_options(self, handler):
        payload = handler(self)
        if self.context_policy == "parent-floor-v2":
            payload.pop("context_policy", None)
        return payload

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Duplicate document scope")
        return self


class VectorHit(Snapshot):
    chunk_id: Identifier
    score: float = Field(allow_inf_nan=False)
    channel: Literal["vector", "lexical"] = "vector"


class EvidenceItem(Snapshot):
    evidence_id: Identifier
    chunk_set_id: Identifier
    chunk: DocumentChunk
    matched_child_ids: tuple[str, ...]
    channels: tuple[str, ...]
    context_start: int = Field(default=0, strict=True, ge=0)
    context_end: int | None = Field(default=None, strict=True, gt=0)

    @property
    def text(self):
        return self.chunk.text[self.context_start:self.context_end]

    @model_serializer(mode="wrap")
    def preserve_historical_item(self, handler):
        payload = handler(self)
        if self.context_start == 0 and self.context_end is None:
            payload.pop("context_start", None)
            payload.pop("context_end", None)
        return payload

    def expected_id(self):
        payload = {"chunk_set_id": self.chunk_set_id, "chunk_id": self.chunk.chunk_id}
        if self.context_start != 0 or self.context_end is not None:
            payload["window"] = (self.context_start, self.context_end)
        return content_id("evidence_", payload)


class EvidenceBundle(Snapshot):
    bundle_id: Identifier
    corpus_id: Identifier
    user_id: int = Field(strict=True, gt=0)
    selector_version: str = "evidence-floor-v2"
    query: str
    options: RetrievalOptions
    items: tuple[EvidenceItem, ...]
    relation_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    context_chars: int = Field(strict=True, ge=0)
    elapsed_ms: int = Field(strict=True, ge=0)

    def expected_id(self):
        # Timing is observational, and must not perturb evidence identity.
        return content_id("bundle_", self.model_dump(mode="json", exclude={"bundle_id", "elapsed_ms"}))


class EvidenceCorpus:
    """One owner's complete immutable ChunkSets. Not an authorization provider.

    SQL loaders must check ownership and source digests before constructing this
    object. Chunk IDs from another snapshot are rejected, even for the same file.
    """
    def __init__(self, user_id: int, chunk_sets: tuple[ChunkSet, ...]):
        if type(user_id) is not int or user_id <= 0 or not chunk_sets:
            raise ValueError("An owner and nonempty corpus are required")
        if len({c.document_id for c in chunk_sets}) != len(chunk_sets) or not all(c.verify() for c in chunk_sets):
            raise ValueError("Duplicate or corrupt ChunkSet")
        self.user_id = user_id
        self.chunk_sets = {c.document_id: c for c in chunk_sets}
        self.chunks = {c.chunk_id: c for s in chunk_sets for c in s.parent_chunks + s.child_chunks}
        self.set_ids = {c.chunk_id: s.chunk_set_id for s in chunk_sets for c in s.parent_chunks + s.child_chunks}
        self.corpus_id = content_id("corpus_", {"owner": user_id, "sets": sorted(s.chunk_set_id for s in chunk_sets)})

    def require_scope(self, user_id: int, document_ids: tuple[str, ...]):
        if user_id != self.user_id:
            raise LookupError("Corpus not found")
        if not document_ids or any(d not in self.chunk_sets for d in document_ids):
            raise LookupError("Document not in corpus")

    def validate_item(self, item: EvidenceItem):
        chunk = self.chunks.get(item.chunk.chunk_id)
        if (chunk != item.chunk or self.set_ids.get(item.chunk.chunk_id) != item.chunk_set_id
                or item.evidence_id != item.expected_id()):
            raise ValueError("Evidence provenance mismatch")
        if not item.matched_child_ids or not set(item.channels) <= {"vector", "graph", "lexical"}:
            raise ValueError("Invalid evidence retrieval provenance")
        end = len(chunk.text) if item.context_end is None else item.context_end
        windowed = item.context_start != 0 or item.context_end is not None
        if not 0 <= item.context_start < end <= len(chunk.text) or windowed and not chunk.is_parent:
            raise ValueError("Invalid context window")
        for matched_id in item.matched_child_ids:
            matched = self.chunks.get(matched_id)
            if (matched is None or matched.document_id != chunk.document_id
                    or matched_id != chunk.chunk_id and matched.parent_chunk_id != chunk.chunk_id):
                raise ValueError("Matched hit does not belong to selected context")
            if windowed:
                start = chunk.text.find(matched.text)
                if (start < 0 or chunk.text.count(matched.text) != 1 or start < item.context_start
                        or start + len(matched.text) > end):
                    raise ValueError("Context window lost or ambiguously maps a retrieved child")


class VectorRetriever(Protocol):
    def search(self, user_id: int, query: str, document_ids: tuple[str, ...], top_k: int) -> list[VectorHit]: ...


class HybridEvidenceEngine:
    """Fuse vector and source-backed graph candidates, then select bounded context.

    Per-document round-robin prevents a high-scoring paper from spending the
    entire budget. It is coverage allocation, not a relevance guarantee. Graph
    outages fall back to vector hits; vector/provenance errors fail closed.
    """
    def __init__(self, corpus: EvidenceCorpus, retriever: VectorRetriever, graph=None):
        self.corpus, self.retriever, self.graph = corpus, retriever, graph

    def search(self, user_id: int, query: str, options: RetrievalOptions) -> EvidenceBundle:
        self.corpus.require_scope(user_id, options.document_ids)
        if not query.strip() or len(query) > 4000:
            raise ValueError("Invalid research query")
        started = perf_counter()
        hits = self.retriever.search(user_id, query, options.document_ids, options.top_k)
        scores, channels, warnings, edges = defaultdict(float), defaultdict(set), [], []
        for rank, hit in enumerate(hits):
            chunk = self.corpus.chunks.get(hit.chunk_id)
            if chunk is None or chunk.is_parent or chunk.document_id not in options.document_ids or not math.isfinite(hit.score):
                raise ValueError("Retriever returned out-of-scope evidence")
            if hit.channel not in channels[hit.chunk_id]:
                scores[hit.chunk_id] += 1 / (60 + rank + 1)
            channels[hit.chunk_id].add(hit.channel)
        if options.include_graph and self.graph is not None:
            try:
                edges = self.graph.retrieve(user_id, query, options.document_ids, options.top_k, self.corpus)
            except Exception:
                warnings.append("graph_unavailable_vector_fallback")
            for rank, edge in enumerate(edges):
                chunk_id = edge.citation.chunk_id
                chunk = self.corpus.chunks.get(chunk_id)
                if chunk is None or chunk.document_id not in options.document_ids:
                    raise ValueError("Graph returned out-of-scope evidence")
                if "graph" not in channels[chunk_id]:
                    scores[chunk_id] += 1 / (60 + rank + 1)
                channels[chunk_id].add("graph")
            if edges:
                warnings.append("graph_relations_are_source_backed_hypotheses")
        queues = {d: [] for d in options.document_ids}
        for chunk_id in sorted(scores, key=lambda i: (-scores[i], i)):
            queues[self.corpus.chunks[chunk_id].document_id].append(chunk_id)
        selected, used, total = [], {}, 0
        seed_limit = options.max_context_chars
        precise_index_query = '索引' in query or bool(re.search(r'\bindex(?:es|ing)?\b',query,re.IGNORECASE))
        if options.expand_parents and options.context_policy == "local-window-v3" and not precise_index_query:
            seed_limit = max(1, options.max_context_chars * 4 // 5)
        while any(queues.values()) and len(selected) < options.max_items:
            for document_id in options.document_ids:
                if len(selected) >= options.max_items:
                    break
                queue = queues[document_id]
                if not queue:
                    continue
                child_id = queue.pop(0)
                child = self.corpus.chunks[child_id]
                chunk = child
                if total + len(chunk.text) > options.max_context_chars:
                    warnings.append("candidate_budget_exceeded")
                    continue
                if selected and total + len(chunk.text) > seed_limit:
                    warnings.append("context_expansion_budget_reserved")
                    continue
                if chunk.chunk_id in used:
                    continue
                item = EvidenceItem(evidence_id="pending", chunk_set_id=self.corpus.set_ids[chunk.chunk_id],
                    chunk=chunk, matched_child_ids=(child_id,), channels=tuple(sorted(channels[child_id])))
                item = item.model_copy(update={"evidence_id": item.expected_id()})
                used[chunk.chunk_id] = len(selected)
                selected.append(item)
                total += len(chunk.text)
        # Evidence floor: first select child context. The opt-in window policy
        # reserves 20% for expansion; the historical policy keeps its full floor.
        # Upgrade
        # complete parent groups only when all selected children remain covered
        # and the net context fits. Never discard a hit to buy more background.
        if options.expand_parents:
            parent_order = list(dict.fromkeys(i.chunk.parent_chunk_id for i in selected if not i.chunk.is_parent))
            for parent_id in parent_order:
                parent = self.corpus.chunks[parent_id]
                members = [n for n, i in enumerate(selected) if i.chunk.parent_chunk_id == parent_id or i.chunk.chunk_id == parent_id]
                old_size = sum(len(selected[n].text) for n in members)
                new_total = total - old_size + len(parent.text)
                window = None
                if new_total > options.max_context_chars:
                    warnings.append("parent_budget_exceeded")
                    if options.context_policy == "local-window-v3":
                        window = _compact_window(self.corpus, parent, [selected[n] for n in members],
                            options.max_context_chars - total + old_size)
                    if window is None:
                        continue
                    new_total = total - old_size + window[1] - window[0]
                    warnings.append("compact_parent_window")
                children = tuple(sorted({c for n in members for c in selected[n].matched_child_ids}))
                merged_channels = tuple(sorted({c for n in members for c in selected[n].channels}))
                item = EvidenceItem(evidence_id="pending", chunk_set_id=self.corpus.set_ids[parent_id],
                    chunk=parent, matched_child_ids=children, channels=merged_channels,
                    **({"context_start": window[0], "context_end": window[1]} if window else {}))
                item = item.model_copy(update={"evidence_id": item.expected_id()})
                first = members[0]
                selected = [item if n == first else i for n, i in enumerate(selected) if n == first or n not in members]
                total = new_total
        covered = {i.chunk.document_id for i in selected}
        warnings.extend("no_context_for_document:" + d for d in options.document_ids if d not in covered)
        selected_ids = {i.chunk.chunk_id for i in selected} | {c for i in selected for c in i.matched_child_ids}
        bundle = EvidenceBundle(bundle_id="pending", corpus_id=self.corpus.corpus_id, user_id=user_id,
            selector_version="evidence-window-v3" if options.context_policy == "local-window-v3" else "evidence-floor-v2",
            query=query, options=options, items=tuple(selected),
            relation_ids=tuple(sorted(e.relation_id for e in edges if e.citation.chunk_id in selected_ids)),
            warnings=tuple(sorted(set(warnings))), context_chars=total,
            elapsed_ms=round((perf_counter() - started) * 1000))
        return bundle.model_copy(update={"bundle_id": bundle.expected_id()})


def _compact_window(corpus, parent, selected, limit):
    """Add one nearest stored sibling while keeping every selected child.

    Repeated parent text is ambiguous and deliberately falls back to children.
    This is a source interval, never a newly fabricated or indexed chunk.
    """
    ids = {c for item in selected for c in item.matched_child_ids}
    children = [c for c in corpus.chunk_sets[parent.document_id].child_chunks if c.parent_chunk_id == parent.chunk_id]
    positions = {}
    for child in children:
        if parent.text.count(child.text) == 1:
            start = parent.text.index(child.text)
            positions[child.chunk_id] = (start, start + len(child.text))
    if not ids <= positions.keys():
        return None
    left = min(positions[i][0] for i in ids)
    right = max(positions[i][1] for i in ids)
    indexes = [c.chunk_index for c in children if c.chunk_id in ids]
    candidates = sorted((c for c in children if c.chunk_id not in ids and c.chunk_id in positions),
        key=lambda c: (min(abs(c.chunk_index - i) for i in indexes), c.chunk_index))
    for child in candidates:
        start, end = positions[child.chunk_id]
        window = min(left, start), max(right, end)
        if window[1] - window[0] <= limit:
            return window
    return None
