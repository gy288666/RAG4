"""Citation copying failures reproduced at the real extraction/tool boundary."""
import pytest

from app.research.artifacts import extract_claims
from app.research.evidence import HybridEvidenceEngine, RetrievalOptions
from app.research.tools import comparison_tools, ToolContext
from app.research.tasks import BundleRef
from test_research_evidence import corpus_for, Hits


def test_citation_handles_remove_model_quote_copying_from_extraction():
    text = "FiD encodes each passage independently.\nThe decoder attends to all passage representations."
    corpus = corpus_for(text, parent_size=180, child_size=100)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "method", RetrievalOptions(document_ids=("d0",)))

    class Model:
        extraction_protocol = "source-handles-v2"

        def generate(self, operation, payload):
            assert operation == "extract_cited"
            citation = payload["citations"][0]
            return {"claims": [{"facet": "method", "statement": "FiD 独立编码每个段落。",
                "citation_id": citation["citation_id"]}], "relations": []}

    claims, _, warnings = extract_claims(Model(), corpus, "d0", bundle, "compare")
    assert len(claims) == 1 and not warnings
    claims[0].citation.validate_source(corpus, "d0")
    assert "independently" in claims[0].citation.quote


def test_schema_failure_records_safe_constraint_not_untrusted_output(workflow):
    # Imported fixture belongs to test_research_agent; the registered tool is
    # the seam which originally saved only an opaque ValidationError.
    task, corpus, _, _, _, context_factory = workflow
    context = context_factory(task)
    bundle = context.engine.search(task.user_id, "method", RetrievalOptions(document_ids=("d0",)))
    task = task.model_copy(update={"bundles": (BundleRef.capture(bundle),)})

    class BadModel:
        def generate(self, *args):
            return {"claims": [{"facet": "method", "statement": "private-user-text",
                "evidence_id": bundle.items[0].evidence_id}], "private-token-key": "private-secret"}

    result = comparison_tools().execute("compare_evidence", ToolContext(task, corpus, context.engine, BadModel()),
        {"document_id": "d0"})
    assert result.status == "failed"
    assert "response_schema_invalid:extract:claims.0.quote:missing" in result.warnings
    serialized = result.model_dump_json()
    assert "private-user-text" not in serialized and "private-token-key" not in serialized and "private-secret" not in serialized


def test_quote_rejection_explains_missing_vs_ambiguous_without_copying_text():
    corpus = corpus_for("DPR uses BERT. DPR uses BERT.", parent_size=180, child_size=100)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "method", RetrievalOptions(document_ids=("d0",)))

    class Model:
        def generate(self, *args):
            return {"claims": [{"facet": "method", "statement": "Claim", "evidence_id": bundle.items[0].evidence_id,
                "quote": "DPR uses BERT."}], "relations": []}

    claims, _, warnings = extract_claims(Model(), corpus, "d0", bundle, "compare")
    assert not claims
    assert "draft_claim_rejected:method:ambiguous_quote" in warnings


def test_catalog_is_disjoint_bounded_stable_and_source_complete():
    from app.research.artifacts import citation_catalog
    text = "Model architecture. " * 190
    corpus = corpus_for(text, parent_size=5000, child_size=500)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "method", RetrievalOptions(
        document_ids=("d0",), max_context_chars=5000))
    catalog = citation_catalog(bundle)
    assert list(catalog) == list(citation_catalog(bundle))
    assert sum(end-start for _, start, end in catalog.values()) == bundle.context_chars
    for item in bundle.items:
        fragments = [(start, end) for chunk, start, end in catalog.values() if chunk == item]
        assert fragments[0][0] == 0 and fragments[-1][1] == len(item.chunk.text)
        assert all(end-start <= 1600 for start, end in fragments)
        assert all(a[1] == b[0] for a, b in zip(fragments, fragments[1:]))


def test_unknown_handle_is_rejected_and_numeric_gate_still_applies():
    from app.research.artifacts import EvidenceVerifier
    corpus = corpus_for("NQ dev exact match score is 38.5.", parent_size=180, child_size=100)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "result", RetrievalOptions(document_ids=("d0",)))

    class Model:
        extraction_protocol = "source-handles-v2"
        calls = 0

        def generate(self, operation, payload):
            self.calls += 1
            return {"claims": [
                {"facet": "result", "statement": "NQ dev exact match 38.2", "citation_id": payload["citations"][0]["citation_id"]},
                {"facet": "method", "statement": "invented", "citation_id": "foreign-citation"}], "relations": []}

    model = Model()
    claims, _, warnings = extract_claims(model, corpus, "d0", bundle, "compare")
    assert len(claims) == 1 and "draft_claim_rejected:method:unknown_citation" in warnings
    report = EvidenceVerifier(model).verify(corpus, claims)
    assert report.supported == 0 and model.calls == 1
    assert report.verdicts[0].reason == "numeric_value_not_in_quote"


def test_bounded_extra_candidates_do_not_discard_other_facets():
    # Reproduces the observed claims:too_long failure. The exact historical
    # response was not captured; these are controlled source-backed candidates.
    corpus = corpus_for("NQ dev exact match score is 38.5. DPR uses BERT.", parent_size=180, child_size=100)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "result", RetrievalOptions(document_ids=("d0",)))

    class Model:
        extraction_protocol = "source-handles-v2"

        def generate(self, operation, payload):
            return {"claims": [{"facet": facet, "statement": "Controlled candidate", "citation_id": payload["citations"][0]["citation_id"]}
                for facet in ("method", "method", "dataset", "result", "limitation")], "relations": []}

    claims, _, warnings = extract_claims(Model(), corpus, "d0", bundle, "compare")
    assert tuple(c.facet for c in claims) == ("method", "dataset", "result", "limitation")
    assert "candidate_claim_count:5" in warnings
    assert "draft_claim_rejected:method:duplicate_facet" in warnings


def test_candidate_input_bound_and_schema_remain_strict():
    from app.research.protocol import ResponseSchemaError
    corpus = corpus_for("DPR uses BERT.", parent_size=180, child_size=100)
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "model", RetrievalOptions(document_ids=("d0",)))

    class Model:
        extraction_protocol = "source-handles-v2"

        def generate(self, operation, payload):
            return {"claims": [{"facet": "method", "statement": "Claim", "citation_id": payload["citations"][0]["citation_id"]}] * 9,
                "relations": []}

    with pytest.raises(ResponseSchemaError) as caught:
        extract_claims(Model(), corpus, "d0", bundle, "compare")
    assert "response_schema_invalid:extract_cited:claims:too_long" in caught.value.diagnostics


def test_json_mode_is_explicit_and_duplicate_json_cannot_override_a_claim():
    import httpx, json
    from app.research.model import CompletionSpec, JsonResearchModel
    spec = CompletionSpec(endpoint="https://model.invalid/chat/completions", model_id="test",
        extraction_protocol="source-handles-v2", response_format="json_object")

    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"claims": [], "claims": [{"private-user-key":"private-text"}]}'}}], "usage": {"total_tokens": 3}})

    model = JsonResearchModel(spec, api_key="not-a-real-secret", max_calls=1, transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError):
        model.generate("extract_cited", {})
    assert model.calls[0]["status"] == "failed" and model.calls[0]["usage"]["total_tokens"] == 3
    assert "private-user-key" not in json.dumps(model.calls)
    legacy = CompletionSpec(endpoint=spec.endpoint, model_id="legacy")
    assert legacy.extraction_protocol == "literal-quote-v1" and legacy.response_format == "text"


# Reuse the task fixture instead of inventing an incomplete task schema.
from test_research_agent import workflow
