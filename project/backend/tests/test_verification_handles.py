"""Source-handle protocol removes quote copying without relaxing provenance."""
import pytest
from test_research_verification_checks import example
from app.research.artifacts import EvidenceVerifier, ArtifactComposer


class HandleModel:
    verification_protocol = "source-handles-v4"

    def __init__(self, invalid=False):
        self.invalid = invalid

    def generate(self, operation, payload):
        assert operation == "verify_handles"
        return {"assessments": [{"claim_id": c["claim_id"], **{
            name: {"status": "supported", "reason": "Explicit evidence",
                "support_ids": ["foreign" if self.invalid else c["sources"][0]["source_id"]]}
            for name in ("attribution", "conditions", "entailment")}} for c in payload["claims"]]}


def test_handles_resolve_server_side_and_survive_artifact_roundtrip():
    from app.research.artifacts import ComparisonArtifact
    corpus, claim = example()
    report = EvidenceVerifier(HandleModel()).verify(corpus, (claim,))
    assert report.supported == 1 and report.verifier_version == "exact-source-handles-v4"
    check = report.assessments[0].entailment
    assert check.support_ids and check.support_quote in claim.citation.quote
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "Paper"}, (claim,), report)
    restored = ComparisonArtifact.model_validate_json(artifact.model_dump_json())
    assert restored.artifact_id == restored.expected_id()


def test_foreign_handle_cannot_support_a_claim():
    corpus, claim = example()
    report = EvidenceVerifier(HandleModel(invalid=True)).verify(corpus, (claim,))
    assert report.supported == 0
    assert "unknown_support_id" in report.verdicts[0].reason
    assert "Explicit evidence" in report.verdicts[0].reason


def test_verification_catalog_covers_exact_original_with_stable_scoped_ids():
    from app.research.artifacts import verification_sources
    corpus, claim = example()
    catalog = verification_sources(claim)
    assert catalog == verification_sources(claim)
    assert ''.join(x['text'] for x in catalog) == claim.citation.quote
    assert all(claim.citation.quote[x['start']:x['end']] == x['text'] for x in catalog)
    changed = claim.model_copy(update={"claim_id": "other"})
    assert not {x['source_id'] for x in catalog} & {x['source_id'] for x in verification_sources(changed)}


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "other_claim", "copied_quote"])
def test_bad_support_selection_cannot_publish(mutation):
    from app.research.artifacts import verification_sources
    from app.research.protocol import ResponseSchemaError
    corpus, claim = example()
    model = HandleModel()
    original = model.generate
    def altered(operation, payload):
        result = original(operation, payload)
        check = result['assessments'][0]['conditions']
        if mutation == 'empty':check['support_ids'] = []
        elif mutation == 'duplicate':check['support_ids'] *= 2
        elif mutation == 'other_claim':
            check['support_ids'] = [verification_sources(claim.model_copy(update={'claim_id': 'another'}))[0]['source_id']]
        else:check['support_quote'] = claim.citation.quote
        return result
    model.generate = altered
    if mutation == 'copied_quote':
        with pytest.raises(ResponseSchemaError):EvidenceVerifier(model).verify(corpus, (claim,))
    else:
        assert EvidenceVerifier(model).verify(corpus, (claim,)).supported == 0


def test_forged_handle_mapping_rejected_by_composer():
    corpus, claim = example()
    report = EvidenceVerifier(HandleModel()).verify(corpus, (claim,))
    assessment = report.assessments[0]
    changed = assessment.model_copy(update={'conditions': assessment.conditions.model_copy(update={'support_ids': ('foreign',)})})
    report = report.model_copy(update={'assessments': (changed,)})
    with pytest.raises(ValueError, match='source checks'):
        ArtifactComposer().compose(corpus, 'compare', ('d0',), {'d0': 'Paper'}, (claim,), report)


def test_quote_protocol_report_serialization_is_unchanged():
    import json
    from pathlib import Path
    from app.research.artifacts import VerificationReport
    saved = json.loads((Path(__file__).resolve().parents[1] / 'evaluation/results/source_checks_20261014.json').read_text(encoding='utf-8'))
    old = saved['runs'][1]['verification']
    assert VerificationReport.model_validate(old).model_dump(mode='json') == old


def test_long_typography_catalog_and_enclosing_span_are_exact():
    from app.research.artifacts import verification_sources, resolve_support
    _, claim = example()
    text = ('A \ufb01ne\n hyphen-\nated sentence. ' * 80)[:2000]
    claim = claim.model_copy(update={'citation': claim.citation.model_copy(update={'quote': text, 'char_end': len(text)})})
    windows = verification_sources(claim)
    assert ''.join(w['text'] for w in windows) == text
    assert resolve_support(claim, (windows[0]['source_id'], windows[1]['source_id'])) == text[:windows[1]['end']]
    assert resolve_support(claim, tuple(w['source_id'] for w in windows)) is None
