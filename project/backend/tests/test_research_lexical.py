"""Sparse retrieval can recover a missing child without borrowing other owners."""
import pytest
from app.research.lexical import LexicalEvidenceRetriever
from app.research.evidence import HybridEvidenceEngine, RetrievalOptions
from test_research_evidence import corpus_for, Hits


def test_sparse_recovers_index_context_not_in_dense_hits_and_records_channel():
    corpus = corpus_for('General encoder architecture.\n\nThe document index is refreshed after training.',
        parent_size=150, child_size=40)
    child = corpus.chunk_sets['d0'].child_chunks[0]
    retriever = LexicalEvidenceRetriever(corpus, Hits(corpus, [child.chunk_id]))
    one = retriever.search(1, '索引更新', ('d0',), 2)
    assert one == retriever.search(1, '索引更新', ('d0',), 2)
    assert len(one) == 2 and any(h.channel == 'lexical' for h in one)
    bundle = HybridEvidenceEngine(corpus, retriever).search(1, '索引更新', RetrievalOptions(document_ids=('d0',)))
    assert any('lexical' in i.channels for i in bundle.items)


def test_foreign_primary_candidate_is_rejected_even_if_it_would_be_outside_cap():
    corpus = corpus_for('Own index refresh.', 'Other paper training.')
    retriever = LexicalEvidenceRetriever(corpus, Hits(corpus))
    with pytest.raises(ValueError):retriever.search(1, 'index', ('d0',), 1)
    with pytest.raises(LookupError):retriever.search(99, 'index', ('d0',), 1)


def test_document_scope_and_candidate_cap_are_strict():
    corpus = corpus_for('Index update. ' * 6, 'Index update. ' * 6)
    ids = [c.chunk_id for c in corpus.chunk_sets['d0'].child_chunks]
    hits = LexicalEvidenceRetriever(corpus, Hits(corpus, ids)).search(1, 'index update', ('d0',), 2)
    assert len({h.chunk_id for h in hits}) <= 2
    assert all(corpus.chunks[h.chunk_id].document_id == 'd0' for h in hits)


def test_generic_questions_preserve_dense_ranking_without_sparse_intrusion():
    corpus = corpus_for('Encoder architecture. Index refresh.',parent_size=150,child_size=25)
    primary = Hits(corpus)
    assert LexicalEvidenceRetriever(corpus,primary).search(1,'compare encoders',('d0',),10) == primary.search(1,'compare encoders',('d0',),10)


def test_sparse_repairs_same_document_and_preserves_other_document_hits():
    corpus = corpus_for('Encoder architecture.\n\nThe document index is refreshed after training.',
        'Index refresh evidence. More fine tuning evidence.',parent_size=150,child_size=40)
    first = corpus.chunk_sets['d0'].child_chunks[0]
    other = corpus.chunk_sets['d1'].child_chunks[0]
    hits = LexicalEvidenceRetriever(corpus,Hits(corpus,[first.chunk_id,other.chunk_id])).search(1,'索引更新',('d0','d1'),2)
    assert other.chunk_id in {h.chunk_id for h in hits}
    assert any(h.channel=='lexical' and corpus.chunks[h.chunk_id].document_id=='d0' for h in hits)


def test_source_role_prefers_own_index_method_over_cited_background():
    text = ('A dense retriever maps questions into vectors.\n\n'
        'Their index update and pretraining index refresh follow Smith et al. and their prior approach.\n\n'
        'During inference we apply the passage encoder to all passages and index them offline.')
    corpus = corpus_for(text,parent_size=400,child_size=110)
    primary = corpus.chunk_sets['d0'].child_chunks[0]
    hits = LexicalEvidenceRetriever(corpus,Hits(corpus,[primary.chunk_id]),source_role=True).search(
        1,'索引更新，区分预训练和微调',('d0',),1)
    assert 'During inference we apply' in corpus.chunks[hits[0].chunk_id].text
    assert hits == LexicalEvidenceRetriever(corpus,Hits(corpus,[primary.chunk_id]),source_role=True).search(
        1,'索引更新，区分预训练和微调',('d0',),1)


def test_source_role_is_opt_in_and_speed_questions_keep_bm25_order():
    corpus = corpus_for('Encoder architecture.\n\n'
        'Their index speed and index update follow Smith et al. and their approach.\n\n'
        'During inference we index passages offline.',parent_size=400,child_size=100)
    primary = Hits(corpus,[corpus.chunk_sets['d0'].child_chunks[0].chunk_id])
    old = LexicalEvidenceRetriever(corpus,primary)
    new = LexicalEvidenceRetriever(corpus,primary,source_role=True)
    assert new.search(1,'索引速度',('d0',),1) == old.search(1,'索引速度',('d0',),1)
    assert new.search(1,'compare encoders',('d0',),1) == primary.search(1,'compare encoders',('d0',),1)


def test_source_role_does_not_replace_existing_index_evidence():
    corpus = corpus_for('Their index update follows Smith et al.\n\n'
        'We apply the encoder and index passages offline.',parent_size=300,child_size=70)
    primary = Hits(corpus,[corpus.chunk_sets['d0'].child_chunks[0].chunk_id])
    assert LexicalEvidenceRetriever(corpus,primary,source_role=True).search(
        1,'index update',('d0',),1) == primary.search(1,'index update',('d0',),1)
