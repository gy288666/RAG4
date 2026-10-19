"""Fail-closed verification at the model/verifier/composer boundary."""
import pytest

from app.research.artifacts import Claim, EvidenceVerifier, ArtifactComposer
from app.research.graph import Citation
from test_research_evidence import corpus_for


def example():
    text = "NQ development set. REALM (X = CC-News): Exact Match 38.5, Recall@5 52.0."
    corpus = corpus_for(text, parent_size=200, child_size=150)
    chunk = corpus.chunk_sets["d0"].child_chunks[0]
    claim = Claim(claim_id="pending", document_id="d0", facet="result",
        statement="REALM achieves 38.5 EM on NQ development.",
        citation=Citation(chunk_id=chunk.chunk_id, char_start=0, char_end=len(text), quote=text))
    return corpus, claim.model_copy(update={"claim_id": claim.expected_id(corpus.corpus_id)})


class CheckedModel:
    verification_protocol = "source-checks-v3"

    def __init__(self, failed=None, fake_quote=False):
        self.failed, self.fake_quote = failed, fake_quote

    def generate(self, operation, payload):
        if operation == "verify":  # Old judge incorrectly approved this real failure pattern.
            return {"verdicts": [{"claim_id": c["claim_id"], "status": "supported", "reason": "Numbers match"}
                for c in payload["claims"]]}
        assert operation == "verify_checked"
        c = payload["claims"][0]
        assert c["facet"] == "result" and c["document_id"] == "d0"
        assert c["source_uri"] == "document:d0"
        checks = {name: {"status": "insufficient" if name == self.failed else "supported",
            "reason": "Missing CC-News condition" if name == self.failed else "Explicit source support",
            "support_quote": "invented evidence" if self.fake_quote else c["quote"]}
            for name in ("attribution", "conditions", "entailment")}
        return {"assessments": [{"claim_id": c["claim_id"], **checks}]}


@pytest.mark.parametrize("failed", ["attribution", "conditions", "entailment"])
def test_one_failed_check_cannot_be_published(failed):
    corpus, claim = example()
    report = EvidenceVerifier(CheckedModel(failed)).verify(corpus, (claim,))
    assert report.supported == 0
    assert failed in report.verdicts[0].reason
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "Paper"}, (claim,), report)
    assert not artifact.citations and artifact.completion_status == "partial"


def test_model_cannot_supply_invented_support_excerpt():
    corpus, claim = example()
    report = EvidenceVerifier(CheckedModel(fake_quote=True)).verify(corpus, (claim,))
    assert report.supported == 0


def test_checks_persist_and_all_required_for_supported():
    corpus, claim = example()
    report = EvidenceVerifier(CheckedModel()).verify(corpus, (claim,))
    assert report.supported == 1
    assert report.verifier_version == "exact-source-checks-v3"
    assert len(report.assessments) == 1


def test_missing_assessment_is_uncertain():
    corpus, claim = example()
    model = CheckedModel()
    model.generate = lambda *args: {"assessments": []}
    report = EvidenceVerifier(model).verify(corpus, (claim,))
    assert report.supported == 0 and report.verdicts[0].reason == "judge_did_not_verify_claim"


@pytest.mark.parametrize("mutation", ["missing_check", "duplicate", "foreign"])
def test_incomplete_or_wrong_claim_protocol_fails_closed(mutation):
    from app.research.protocol import ResponseSchemaError
    corpus, claim = example()
    model = CheckedModel()
    original = model.generate
    def malformed(operation, payload):
        result = original(operation, payload)
        if mutation == "missing_check":
            del result["assessments"][0]["conditions"]
        elif mutation == "duplicate":
            result["assessments"] *= 2
        else:
            result["assessments"][0]["claim_id"] = "foreign"
        return result
    model.generate = malformed
    with pytest.raises((ValueError, ResponseSchemaError)):
        EvidenceVerifier(model).verify(corpus, (claim,))


def test_composer_rechecks_assessments_before_publication():
    corpus, claim = example()
    report = EvidenceVerifier(CheckedModel("conditions")).verify(corpus, (claim,))
    forged = report.model_copy(update={"supported": 1, "verdicts": (
        report.verdicts[0].model_copy(update={"status": "supported"}),)})
    with pytest.raises(ValueError, match="source checks"):
        ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "Paper"}, (claim,), forged)


def test_historical_protocol_and_artifact_digest_stay_readable():
    from pathlib import Path
    from app.research.artifacts import ComparisonArtifact
    from app.research.model import CompletionSpec
    spec = CompletionSpec(endpoint="https://model.example/v1/chat/completions", model_id="test")
    assert spec.verification_protocol == "numeric-model-v2"
    path = Path(__file__).resolve().parents[1] / "evaluation/results/citation_comparison_artifact_20261013.json"
    artifact = ComparisonArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    assert artifact.artifact_id == artifact.expected_id()
    assert "assessments" not in artifact.verification.model_dump()
