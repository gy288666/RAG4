"""Scope/identity tests only; fixture judgments are not semantic accuracy tests."""
import pytest
from app.research.artifacts import EvidenceVerifier, ArtifactComposer
from app.research.verification_context import build_context
from app.research.model import CompletionSpec
from test_verification_context import context_example
from test_verification_facets import FacetModel


def test_support_only_uses_exact_citation_without_neighbor_or_chunk_expansion():
    corpus, claim = context_example()
    legacy = build_context(corpus, claim)
    scoped = build_context(corpus, claim, policy='cited-support-v2')
    assert scoped.text == claim.citation.quote
    assert [p.role for p in scoped.parts] == ['cited']
    assert scoped.parts[0].citation == claim.citation
    assert scoped.context_id != legacy.context_id
    scoped.validate_source(corpus, claim)


def test_verifier_payload_context_does_not_enlarge_publishable_support():
    corpus, claim = context_example()
    model = FacetModel(); model.verification_context_policy = 'cited-support-v2'
    report = EvidenceVerifier(model).verify(corpus, (claim,))
    item = model.payload['claims'][0]
    assert item['context'] == claim.citation.quote
    assert ''.join(s['text'] for s in item['sources']) == claim.citation.quote
    assert len(item['context_sources']) == 1
    assert report.contexts[0].policy == report.context_policy == 'cited-support-v2'
    ArtifactComposer().compose(corpus, 'goal', ('d0', 'd1'), {'d0':'paper0', 'd1':'paper1'}, (claim,), report)


def test_report_policy_cannot_relabel_a_broader_context_as_support_only():
    corpus, claim = context_example()
    model = FacetModel(); model.verification_context_policy = 'preceding-children-v1'
    report = EvidenceVerifier(model).verify(corpus, (claim,))
    relabelled = report.model_copy(update={'context_policy': 'cited-support-v2'})
    with pytest.raises(ValueError):
        ArtifactComposer().compose(corpus, 'goal', ('d0', 'd1'), {'d0':'paper0', 'd1':'paper1'}, (claim,), relabelled)


def test_context_validation_rejects_quote_expansion_under_support_only_policy():
    corpus, claim = context_example()
    old = build_context(corpus, claim)
    falsified = old.model_copy(update={'policy': 'cited-support-v2'})
    with pytest.raises(ValueError): falsified.validate_source(corpus, claim)


def test_unknown_selection_rejected_before_model_call():
    corpus, claim = context_example()
    with pytest.raises(ValueError): build_context(corpus, claim, policy='unknown')


def test_new_policy_is_opt_in_and_requires_faceted_source_handles():
    values = {'endpoint': 'https://example.test/v1/chat/completions', 'model_id': 'fixture'}
    assert CompletionSpec(**values).verification_context_policy == 'cited-chunk-v1'
    with pytest.raises(ValueError): CompletionSpec(**values, verification_context_policy='cited-support-v2')
    assert CompletionSpec(**values, verification_protocol='facet-handles-v5', verification_context_policy='cited-support-v2')
