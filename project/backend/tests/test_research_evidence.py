"""Research evidence contracts exercised without SQL or remote models."""
import pytest

from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.models import ParsedBlock, ParsedDocument, SourceInfo
from app.research.evidence import EvidenceCorpus, HybridEvidenceEngine, RetrievalOptions, VectorHit
from app.research.graph import Citation, GraphRelation, MemoryGraphStore, entity_identity


def corpus_for(*texts, owner=1, parent_size=160, child_size=40):
    sets = []
    for index, text in enumerate(texts):
        doc = ParsedDocument(document_id=f"d{index}", file_name=f"p{index}.pdf", parser_version="test-v1",
            page_count=2, source=SourceInfo(uri=f"document:d{index}"),
            blocks=(ParsedBlock(block_id="b", text=text, page_start=2, page_end=2),))
        sets.append(ChunkingEngine().split(doc, ChunkingConfig(child_max_tokens=child_size, parent_max_tokens=parent_size)))
    return EvidenceCorpus(owner, tuple(sets))


class Hits:
    def __init__(self, corpus, ids=None):
        self.ids = ids if ids is not None else [c.chunk_id for s in corpus.chunk_sets.values() for c in s.child_chunks]

    def search(self, user_id, query, document_ids, top_k):
        return [VectorHit(chunk_id=i, score=1 / (n + 1)) for n, i in enumerate(self.ids)]


def relation_for(corpus, document_id="d0", quote="DPR uses BERT", subject="DPR", object="BERT"):
    chunk = next(c for c in corpus.chunks.values() if c.document_id == document_id and quote in c.text)
    start = chunk.text.index(quote)
    r = GraphRelation(relation_id="pending", document_id=document_id, subject=subject, object=object,
        predicate="uses", citation=Citation(chunk_id=chunk.chunk_id, char_start=start, char_end=start + len(quote), quote=quote))
    return r.model_copy(update={"relation_id": r.expected_id(corpus.corpus_id)})


def test_parent_context_and_document_coverage_are_bounded_and_repeatable():
    corpus = corpus_for("DPR uses BERT. " * 8, "FiD uses T5. " * 8)
    engine = HybridEvidenceEngine(corpus, Hits(corpus))
    options = RetrievalOptions(document_ids=("d0", "d1"), max_context_chars=260)
    one, two = engine.search(1, "encoders", options), engine.search(1, "encoders", options)
    assert one.bundle_id == two.bundle_id
    assert one.context_chars == sum(len(i.chunk.text) for i in one.items) <= 260
    assert {i.chunk.document_id for i in one.items} == {"d0", "d1"}
    assert all(i.chunk.is_parent and i.chunk.page_start == 2 for i in one.items)
    assert len(one.items) == 2  # matching children share one complete parent
    assert all(len(i.matched_child_ids) > 1 for i in one.items)
    for item in one.items:
        corpus.validate_item(item)


def test_small_budget_falls_back_to_complete_child_never_truncates():
    corpus = corpus_for("A long sentence describes an encoder. " * 5)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "encoder",
        RetrievalOptions(document_ids=("d0",), max_context_chars=40))
    assert bundle.items and all(not i.chunk.is_parent for i in bundle.items)
    assert bundle.context_chars <= 40
    assert "parent_budget_exceeded" in bundle.warnings
    empty = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "encoder",
        RetrievalOptions(document_ids=("d0",), max_context_chars=1))
    assert empty.items == () and "no_context_for_document:d0" in empty.warnings


def test_ownership_and_foreign_retrieval_fail_closed():
    corpus = corpus_for("Own evidence.")
    engine = HybridEvidenceEngine(corpus, Hits(corpus))
    with pytest.raises(LookupError):
        engine.search(2, "evidence", RetrievalOptions(document_ids=("d0",)))
    with pytest.raises(LookupError):
        engine.search(1, "evidence", RetrievalOptions(document_ids=("other",)))
    with pytest.raises(ValueError, match="out-of-scope"):
        HybridEvidenceEngine(corpus, Hits(corpus, ["other-snapshot"])).search(1, "evidence",
            RetrievalOptions(document_ids=("d0",)))


def test_graph_publishes_atomically_validates_mentions_and_removes_sources():
    corpus = corpus_for("DPR uses BERT. FiD uses T5.")
    graph = MemoryGraphStore()
    good = relation_for(corpus)
    graph.replace_document(1, "d0", (good,), corpus)
    bad = good.model_copy(update={"object": "invented"})
    bad = bad.model_copy(update={"relation_id": bad.expected_id(corpus.corpus_id)})
    with pytest.raises(ValueError):
        graph.replace_document(1, "d0", (bad,), corpus)
    assert graph.retrieve(1, "BERT", ("d0",), 5, corpus) == [good]
    other = corpus_for("DPR uses BERT. FiD uses T5.", owner=2)
    assert graph.retrieve(2, "BERT", ("d0",), 5, other) == []
    newer = corpus_for("DPR now uses something else.")
    assert graph.retrieve(1, "BERT", ("d0",), 5, newer) == []
    graph.remove_document(1, "d0")
    assert graph.retrieve(1, "BERT", ("d0",), 5, corpus) == []


def test_graph_can_supply_source_backed_context_and_outages_degrade():
    corpus = corpus_for("DPR uses BERT.")
    graph = MemoryGraphStore()
    relation = relation_for(corpus)
    graph.replace_document(1, "d0", (relation,), corpus)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus, []), graph).search(1, "BERT",
        RetrievalOptions(document_ids=("d0",)))
    assert bundle.relation_ids == (relation.relation_id,)
    assert bundle.items[0].channels == ("graph",)

    class OfflineGraph:
        def retrieve(self, *args):
            raise ConnectionError("private server detail")

    fallback = HybridEvidenceEngine(corpus, Hits(corpus), OfflineGraph()).search(1, "BERT",
        RetrievalOptions(document_ids=("d0",)))
    assert fallback.items and fallback.warnings == ("graph_unavailable_vector_fallback",)


def test_tampered_citation_cannot_enter_graph():
    corpus = corpus_for("DPR uses BERT.")
    good = relation_for(corpus)
    bad = good.model_copy(update={"citation": good.citation.model_copy(update={"char_end": 200})})
    with pytest.raises(ValueError):
        MemoryGraphStore().replace_document(1, "d0", (bad,), corpus)


def test_parent_expansion_preserves_every_selected_child_under_same_budget():
    corpus = corpus_for("Architecture and important evidence. " * 12, "Independent experiment results. " * 10,
        parent_size=160, child_size=40)
    engine = HybridEvidenceEngine(corpus, Hits(corpus))
    for budget in (40, 100, 160, 300, 600):
        options = RetrievalOptions(document_ids=("d0", "d1"), max_items=10, max_context_chars=budget, expand_parents=False)
        baseline = engine.search(1, "results", options)
        expanded = engine.search(1, "results", options.model_copy(update={"expand_parents": True}))
        for item in baseline.items:
            assert any(item.chunk.chunk_id == chosen.chunk.chunk_id or item.chunk.parent_chunk_id == chosen.chunk.chunk_id for chosen in expanded.items)
        assert expanded.context_chars <= budget


def test_cross_document_two_hop_paths_keep_each_source_and_enforce_scope():
    corpus = corpus_for("DPR uses BERT.", "BERT uses pretraining.")
    graph = MemoryGraphStore()
    first = relation_for(corpus)
    second = relation_for(corpus, "d1", "BERT uses pretraining", "BERT", "pretraining")
    graph.replace_document(1, "d0", (first,), corpus)
    graph.replace_document(1, "d1", (second,), corpus)
    entity = entity_identity(1, "DPR")
    view = graph.explore(1, entity, ("d0", "d1"), corpus)
    assert len(view.entities) == 3 and len(view.relations) == 2
    assert any(p.relation_ids == (first.relation_id, second.relation_id) for p in view.paths)
    assert {r.document_id for r in view.relations} == {"d0", "d1"}
    limited = graph.explore(1, entity, ("d0",), corpus)
    assert len(limited.relations) == 1
    assert entity_identity(1, "BERT") == entity_identity(1, "bert")
    assert entity_identity(1, "BERT") != entity_identity(2, "BERT")
    with pytest.raises(ValueError):
        graph.explore(1, entity, ("d0", "d1"), corpus, depth=3)
    graph.remove_document(1, "d1")
    assert len(graph.explore(1, entity, ("d0", "d1"), corpus).relations) == 1
