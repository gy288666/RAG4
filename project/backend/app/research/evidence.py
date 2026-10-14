"""Version-bound evidence selection with a hard Unicode character budget.

No mutable active pointer is consulted here. Callers supply an owned, verified
corpus and a retriever bound to the same snapshot. Entire chunks are selected;
text is never truncated while retaining a locator for a larger passage.
"""
from __future__ import annotations

from collections import defaultdict
import math
from time import perf_counter
from typing import Protocol

from pydantic import Field, model_validator

from app.chunking.models import ChunkSet, DocumentChunk, Identifier, Snapshot, content_id


class RetrievalOptions(Snapshot):
    document_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=5)
    top_k: int = Field(default=10, strict=True, ge=1, le=20)
    max_items: int = Field(default=10, strict=True, ge=1, le=20)
    max_context_chars: int = Field(default=6000, strict=True, ge=1, le=40000)
    expand_parents: bool = True
    include_graph: bool = True

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Duplicate document scope")
        return self


class VectorHit(Snapshot):
    chunk_id: Identifier
    score: float = Field(allow_inf_nan=False)


class EvidenceItem(Snapshot):
    evidence_id: Identifier
    chunk_set_id: Identifier
    chunk: DocumentChunk
    matched_child_ids: tuple[str, ...]
    channels: tuple[str, ...]

    def expected_id(self):
        return content_id("evidence_", {"chunk_set_id": self.chunk_set_id, "chunk_id": self.chunk.chunk_id})


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
        if not item.matched_child_ids or not set(item.channels) <= {"vector", "graph"}:
            raise ValueError("Invalid evidence retrieval provenance")
        for matched_id in item.matched_child_ids:
            matched = self.chunks.get(matched_id)
            if (matched is None or matched.document_id != chunk.document_id
                    or matched_id != chunk.chunk_id and matched.parent_chunk_id != chunk.chunk_id):
                raise ValueError("Matched hit does not belong to selected context")


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
            if "vector" not in channels[hit.chunk_id]:
                scores[hit.chunk_id] += 1 / (60 + rank + 1)
            channels[hit.chunk_id].add("vector")
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
                if chunk.chunk_id in used:
                    continue
                item = EvidenceItem(evidence_id="pending", chunk_set_id=self.corpus.set_ids[chunk.chunk_id],
                    chunk=chunk, matched_child_ids=(child_id,), channels=tuple(sorted(channels[child_id])))
                item = item.model_copy(update={"evidence_id": item.expected_id()})
                used[chunk.chunk_id] = len(selected)
                selected.append(item)
                total += len(chunk.text)
        # Evidence floor: first select exactly the child-only context. Upgrade
        # complete parent groups only when all selected children remain covered
        # and the net context fits. Never discard a hit to buy more background.
        if options.expand_parents:
            parent_order = list(dict.fromkeys(i.chunk.parent_chunk_id for i in selected if not i.chunk.is_parent))
            for parent_id in parent_order:
                parent = self.corpus.chunks[parent_id]
                members = [n for n, i in enumerate(selected) if i.chunk.parent_chunk_id == parent_id or i.chunk.chunk_id == parent_id]
                new_total = total - sum(len(selected[n].chunk.text) for n in members) + len(parent.text)
                if new_total > options.max_context_chars:
                    warnings.append("parent_budget_exceeded")
                    continue
                children = tuple(sorted({c for n in members for c in selected[n].matched_child_ids}))
                merged_channels = tuple(sorted({c for n in members for c in selected[n].channels}))
                item = EvidenceItem(evidence_id="pending", chunk_set_id=self.corpus.set_ids[parent_id],
                    chunk=parent, matched_child_ids=children, channels=merged_channels)
                item = item.model_copy(update={"evidence_id": item.expected_id()})
                first = members[0]
                selected = [item if n == first else i for n, i in enumerate(selected) if n == first or n not in members]
                total = new_total
        covered = {i.chunk.document_id for i in selected}
        warnings.extend("no_context_for_document:" + d for d in options.document_ids if d not in covered)
        selected_ids = {i.chunk.chunk_id for i in selected} | {c for i in selected for c in i.matched_child_ids}
        bundle = EvidenceBundle(bundle_id="pending", corpus_id=self.corpus.corpus_id, user_id=user_id,
            query=query, options=options, items=tuple(selected),
            relation_ids=tuple(sorted(e.relation_id for e in edges if e.citation.chunk_id in selected_ids)),
            warnings=tuple(sorted(set(warnings))), context_chars=total,
            elapsed_ms=round((perf_counter() - started) * 1000))
        return bundle.model_copy(update={"bundle_id": bundle.expected_id()})
