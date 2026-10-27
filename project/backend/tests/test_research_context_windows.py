"""Compact context keeps retrieved evidence and exact parent citation offsets."""
import pytest
from app.research.evidence import HybridEvidenceEngine, RetrievalOptions
from app.research.artifacts import extract_claims
from app.research.tasks import BundleRef
from test_research_evidence import corpus_for, Hits


def window_bundle():
    corpus = corpus_for('Alpha first detail. Bravo second detail. Charlie third detail. Delta final detail.',
        parent_size=150, child_size=30)
    children = corpus.chunk_sets['d0'].child_chunks
    hit = children[-1]
    bundle = HybridEvidenceEngine(corpus, Hits(corpus, [hit.chunk_id])).search(1, 'detail',
        RetrievalOptions(document_ids=('d0',), top_k=1, max_items=1,
            max_context_chars=55, context_policy='local-window-v3'))
    return corpus, hit, bundle


def test_window_keeps_selected_child_under_same_item_and_character_limits():
    corpus, hit, bundle = window_bundle()
    assert len(bundle.items) == 1 and len(hit.text) < bundle.context_chars <= 55
    item = bundle.items[0]
    assert item.chunk.is_parent and hit.text in item.text
    assert item.context_start > 0
    assert item.text == item.chunk.text[item.context_start:item.context_end]
    corpus.validate_item(item)
    assert BundleRef.capture(bundle).hydrate(corpus).bundle_id == bundle.bundle_id


def test_window_citation_is_mapped_to_original_parent_not_local_zero():
    corpus, _, bundle = window_bundle()
    class Model:
        extraction_protocol = 'source-handles-v2'
        def generate(self, operation, payload):
            return {'claims': [{'facet': 'method', 'statement': 'Evidence summary',
                'citation_id': payload['citations'][0]['citation_id']}], 'relations': []}
    claims, _, _ = extract_claims(Model(), corpus, 'd0', bundle, 'compare')
    citation = claims[0].citation
    assert citation.char_start == bundle.items[0].context_start > 0
    assert citation.quote == bundle.items[0].text
    citation.validate_source(corpus, 'd0')


def test_window_cannot_hide_retrieved_child():
    corpus, _, bundle = window_bundle()
    item = bundle.items[0]
    forged = item.model_copy(update={'context_end': item.context_start + 1})
    forged = forged.model_copy(update={'evidence_id': forged.expected_id()})
    with pytest.raises(ValueError):corpus.validate_item(forged)
