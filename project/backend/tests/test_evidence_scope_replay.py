"""Offline diagnostic keeps production provenance and budget gates."""
import pytest
from test_research_evidence import corpus_for
from scripts.evaluate_evidence_scope import replay_scope


def fixture_hits():
    corpus = corpus_for('DPR uses BERT.', 'FiD uses T5.', 'REALM uses BERT.')
    hits = [{'id': s.child_chunks[0].chunk_id, 'text': s.child_chunks[0].text, 'score': 1.0}
        for s in corpus.chunk_sets.values()]
    return corpus, hits


def test_explicit_scope_removes_unselected_documents_without_refilling_or_expanding_budget():
    corpus, hits = fixture_hits()
    for scope in (('d0','d1','d2'), ('d0','d1')):
        bundle = replay_scope(corpus, hits, 'compare', scope, budget=40)
        assert bundle.context_chars <= 40
        assert all(item.chunk.document_id in scope for item in bundle.items)
        assert all(c in {h['id'] for h in hits} for item in bundle.items for c in item.matched_child_ids)
        assert bundle.bundle_id == replay_scope(corpus, hits, 'compare', scope, budget=40).bundle_id


def test_excluded_document_cannot_hide_corrupt_frozen_candidate():
    corpus, hits = fixture_hits()
    hits[-1]['text'] = 'changed'
    with pytest.raises(ValueError, match='mismatch'):
        replay_scope(corpus, hits, 'compare', ('d0','d1'))


def test_unknown_document_scope_rejected():
    corpus, hits = fixture_hits()
    with pytest.raises(LookupError):
        replay_scope(corpus, hits, 'compare', ('foreign',))
