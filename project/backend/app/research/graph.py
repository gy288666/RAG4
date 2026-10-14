"""Small source-backed graph; relations remain hypotheses until verified.

No Neo4j dependency or automatic corpus-wide extraction. Atomic per-document
replacement validates every literal mention and citation before publishing.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from typing import Literal, Protocol

from pydantic import Field

from app.chunking.models import Identifier, Snapshot, content_id
from .evidence import EvidenceCorpus


class Citation(Snapshot):
    chunk_id: Identifier
    char_start: int = Field(strict=True, ge=0)
    char_end: int = Field(strict=True, gt=0)
    quote: str = Field(min_length=1, max_length=4000)

    def validate_source(self, corpus: EvidenceCorpus, document_id: str):
        chunk = corpus.chunks.get(self.chunk_id)
        if (chunk is None or chunk.document_id != document_id or self.char_end <= self.char_start
                or chunk.text[self.char_start:self.char_end] != self.quote or self.char_end > len(chunk.text)):
            raise ValueError("Citation is not an exact slice of the frozen source")


class GraphRelation(Snapshot):
    relation_id: Identifier
    document_id: Identifier
    subject: Identifier
    predicate: Literal["uses", "evaluates_on", "reports", "contrasts", "limits"]
    object: Identifier
    citation: Citation
    status: Literal["provenance_checked"] = "provenance_checked"

    def expected_id(self, corpus_id: str):
        return content_id("relation_", {"corpus_id": corpus_id,
            **self.model_dump(mode="json", exclude={"relation_id"})})


class GraphStore(Protocol):
    def replace_document(self, user_id: int, document_id: str, relations: tuple[GraphRelation, ...], corpus: EvidenceCorpus) -> None: ...
    def retrieve(self, user_id: int, query: str, document_ids: tuple[str, ...], limit: int, corpus: EvidenceCorpus) -> list[GraphRelation]: ...
    def remove_document(self, user_id: int, document_id: str) -> None: ...
    def explore(self, user_id: int, entity_id: str, document_ids: tuple[str, ...], corpus: EvidenceCorpus, *, depth: int = 2, limit: int = 20): ...


class EntityMention(Snapshot):
    document_id: Identifier
    citation: Citation


class GraphEntity(Snapshot):
    entity_id: Identifier
    label: Identifier
    mentions: tuple[EntityMention, ...]


class GraphPath(Snapshot):
    entity_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]


class GraphView(Snapshot):
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]
    paths: tuple[GraphPath, ...]
    warnings: tuple[str, ...] = ("source_backed_hypotheses_not_semantic_proof",)


def entity_identity(user_id, label):
    """Join identical normalized mentions; never invent entity aliases."""
    normalized = " ".join(unicodedata.normalize("NFKC", label).casefold().split())
    return content_id("entity_", {"user_id": user_id, "label": normalized})


class MemoryGraphStore:
    """Process-local, owner + corpus isolated. No semantic truth guarantee.

    Passing the current corpus also fences stale relations after rechunking or
    deletion. remove_document erases all corpus revisions for that owner/file.
    """
    def __init__(self):
        self._relations = {}
        self._lock = threading.RLock()

    def replace_document(self, user_id, document_id, relations, corpus):
        corpus.require_scope(user_id, (document_id,))
        if len(relations) > 100 or len({r.relation_id for r in relations}) != len(relations):
            raise ValueError("Too many or duplicate relations")
        for relation in relations:
            relation.citation.validate_source(corpus, document_id)
            if (relation.document_id != document_id or relation.relation_id != relation.expected_id(corpus.corpus_id)
                    or relation.subject.casefold() not in relation.citation.quote.casefold()
                    or relation.object.casefold() not in relation.citation.quote.casefold()):
                raise ValueError("Relation mentions or identity lack valid source")
        with self._lock:
            self._relations[user_id, corpus.corpus_id, document_id] = relations

    def retrieve(self, user_id, query, document_ids, limit, corpus):
        corpus.require_scope(user_id, document_ids)
        if not 1 <= limit <= 20:
            raise ValueError("Invalid graph limit")
        terms = set(re.findall(r"\w+", query.casefold()))
        with self._lock:
            relations = [r for d in document_ids for r in self._relations.get((user_id, corpus.corpus_id, d), ())]
        ranked = []
        for relation in relations:
            relation.citation.validate_source(corpus, relation.document_id)
            mentions = set(re.findall(r"\w+", (relation.subject + " " + relation.object).casefold()))
            overlap = len(terms & mentions)
            if overlap:
                ranked.append((overlap, relation))
        return [r for _, r in sorted(ranked, key=lambda x: (-x[0], x[1].relation_id))[:limit]]

    def remove_document(self, user_id, document_id):
        with self._lock:
            for key in list(self._relations):
                if key[0] == user_id and key[2] == document_id:
                    del self._relations[key]

    def explore(self, user_id, entity_id, document_ids, corpus, *, depth=2, limit=20):
        """Bounded undirected evidence paths, not causal inference.

        Every hop keeps the asserted predicate's original direction in relations.
        A traversal direction does not reverse or compose those assertions.
        """
        corpus.require_scope(user_id, document_ids)
        if type(depth) is not int or not 1 <= depth <= 2 or type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Graph exploration budget exceeded")
        with self._lock:
            relations = sorted((r for d in document_ids for r in self._relations.get((user_id, corpus.corpus_id, d), ())), key=lambda r: r.relation_id)
        entities, adjacent = {}, {}
        for r in relations:
            r.citation.validate_source(corpus, r.document_id)
            endpoints = []
            for label in (r.subject, r.object):
                identity = entity_identity(user_id, label)
                previous = entities.get(identity)
                mention = EntityMention(document_id=r.document_id, citation=r.citation)
                mentions = previous.mentions if previous else ()
                if mention not in mentions:
                    mentions += (mention,)
                entities[identity] = GraphEntity(entity_id=identity, label=previous.label if previous else label, mentions=mentions)
                endpoints.append(identity)
            left, right = endpoints
            adjacent.setdefault(left, []).append((right, r))
            adjacent.setdefault(right, []).append((left, r))
        if entity_id not in entities:
            return GraphView(entities=(), relations=(), paths=())
        paths, edges, visited_nodes = [], {}, {entity_id}
        frontier = [((entity_id,), ())]
        for _ in range(depth):
            next_frontier = []
            for nodes, path_edges in frontier:
                for neighbor, relation in adjacent.get(nodes[-1], ()):
                    if neighbor in nodes or relation.relation_id in path_edges:
                        continue
                    if relation.relation_id not in edges and len(edges) >= limit:
                        continue
                    new_nodes, new_edges = nodes + (neighbor,), path_edges + (relation.relation_id,)
                    edges[relation.relation_id] = relation
                    visited_nodes.add(neighbor)
                    paths.append(GraphPath(entity_ids=new_nodes, relation_ids=new_edges))
                    next_frontier.append((new_nodes, new_edges))
                    if len(paths) >= limit:
                        return GraphView(entities=tuple(entities[i] for i in sorted(visited_nodes)),
                            relations=tuple(edges[i] for i in sorted(edges)), paths=tuple(paths))
            frontier = next_frontier
        return GraphView(entities=tuple(entities[i] for i in sorted(visited_nodes)),
            relations=tuple(edges[i] for i in sorted(edges)), paths=tuple(paths))
