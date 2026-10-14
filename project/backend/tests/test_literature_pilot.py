"""Meaningful pilot safeguards; no remote models or downloaded PDFs required."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import fitz
import httpx
import pytest
from pydantic import ValidationError

from app.evaluation.literature import (Candidate, Evidence, Paper, Pilot, Question, Span,
    evidence_metrics, load_documents, locate_evidence, make_candidates, validate_vectors)
from app.modeling.interfaces import ModelDescriptor
from app.services.chunking_service import split_blocks
from app.services.parser_service import ParseResult, TextBlock
from scripts.evaluate_literature import BudgetExceeded, PilotEmbedding, run


@pytest.fixture
def pilot(tmp_path):
    path = tmp_path / "paper.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 50), "A verified passage. Evidence is traceable.")
        pdf.save(path)
    paper = Paper(document_id="paper", title="Synthetic unit-test source", url="https://example.invalid/paper",
        pdf_url="https://example.invalid/paper.pdf", file_name=path.name,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), pages=1, license="self-authored",
        license_url="https://example.invalid/license")
    return Pilot(schema_version="literature-pilot-v1", corpus_version="test-v1", annotation_status="ai_draft",
        papers=(paper,), questions=(Question(id="q1", category="fact", question="What is verified?",
            expected_answer="A passage", evidence=(Evidence(document_id="paper", page=1, anchor="verified passage"),)),
            Question(id="q2", category="unanswerable", question="How much does it cost?",
                expected_answer="No price in this corpus")))


class FakeEmbedding:
    descriptor = ModelDescriptor("embedding", "fake", "unit-test-only", "fake-v1", 2)
    def embed_documents(self, texts):
        return [[1.0, 0.5] for _ in texts]


def test_offline_end_to_end_preserves_unanswerable_and_fresh_output(pilot, tmp_path):
    output = tmp_path / "run"
    report = run(pilot, tmp_path, output, FakeEmbedding(), dimension=2)
    assert report["status"] == "succeeded"
    assert report["annotation_status"] == "ai_draft" and report["config"]["llm_answers"] is False
    assert len(report["rows"]) == 4
    for variant in report["variants"].values():
        assert variant["scored_questions"] == variant["unanswerable_not_scored"] == 1
        assert variant["metrics"]["10"]["all_evidence_questions"] == 1
    assert all(row["metrics"] is None for row in report["rows"] if row["category"] == "unanswerable")
    before = (output / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(pilot, tmp_path, output, FakeEmbedding(), dimension=2)
    assert (output / "report.json").read_bytes() == before


def test_changed_pdf_rejected_before_model(pilot, tmp_path):
    (tmp_path / "paper.pdf").write_bytes(b"changed")
    class Forbidden(FakeEmbedding):
        def embed_documents(self, texts):
            pytest.fail("Changed source must fail before model calls")
    report = run(pilot, tmp_path, tmp_path / "run", Forbidden(), dimension=2)
    assert report["status"] == "failed" and report["failure_stage"] == "source_validation"


def test_model_failure_retained_without_secret_message(pilot, tmp_path):
    class Failing(FakeEmbedding):
        def embed_documents(self, texts):
            raise RuntimeError("private-token-must-not-be-persisted")
    output = tmp_path / "run"
    report = run(pilot, tmp_path, output, Failing(), dimension=2)
    assert report["status"] == "failed" and report["failure_stage"] == "query_embedding"
    assert "private-token" not in (output / "report.json").read_text()


def test_wrong_dimension_does_not_silently_drop_hits(pilot, tmp_path):
    report = run(pilot, tmp_path, tmp_path / "run", FakeEmbedding(), dimension=3)
    assert report["status"] == "failed" and report["rows"] == []


def test_nfkc_anchor_offsets_reference_original_text(pilot):
    question = pilot.questions[0].model_copy(update={"evidence": (
        Evidence(document_id="paper", page=1, anchor="file evidence"),)})
    pilot = pilot.model_copy(update={"questions": (question,)})
    documents = {"paper": ParseResult(blocks=[TextBlock("A ﬁle\nevidence is located.", page=1)])}
    span = locate_evidence(pilot, documents)["q1"][0]
    assert documents["paper"].blocks[0].text[span.start:span.end] == "ﬁle\nevidence"


@pytest.mark.parametrize("text", ["missing", "verified passage and verified passage"])
def test_bad_anchor_rejected(pilot, text):
    with pytest.raises(ValueError, match="Ambiguous or missing"):
        locate_evidence(pilot, {"paper": ParseResult(blocks=[TextBlock(text, page=1)])})


def test_wrong_page_rejected(pilot):
    with pytest.raises(ValueError, match="Missing evidence page"):
        locate_evidence(pilot, {"paper": ParseResult(blocks=[TextBlock("verified passage", page=2)])})


def test_legacy_chunks_unchanged_and_both_spans_align():
    text = "First paragraph. " + "Repeated evidence sentence. " * 35
    result = ParseResult(blocks=[TextBlock(text, page=1)], page_count=1)
    variants = make_candidates({"paper": result}, size=100, overlap=20, parent_size=200)
    assert [c.text for c in variants["rag3"]] == [c.text for c in split_blocks(result.blocks, 100, 20)]
    for variant in variants.values():
        for chunk in variant:
            assert all(text[s.start:s.end] in chunk.text for s in chunk.spans)


def test_full_evidence_requires_union_without_gaps_and_correct_document():
    gold = (Span("a", 1, 10, 20), Span("b", 1, 10, 20))
    def candidate(doc, start, end, page=1):
        return Candidate(f"{doc}-{start}", doc, start, "evidence", (Span(doc, page, start, end),))
    hits = [candidate("a", 10, 15), candidate("a", 15, 20), candidate("b", 10, 20)]
    assert evidence_metrics(gold, hits, (1, 2, 3))["metrics"] == {
        "1": {"anchor_span_recall": 0.0, "all_evidence_covered": False},
        "2": {"anchor_span_recall": 0.5, "all_evidence_covered": False},
        "3": {"anchor_span_recall": 1.0, "all_evidence_covered": True}}
    assert evidence_metrics((gold[0],), [hits[0], candidate("a", 16, 20)], (2,))["metrics"]["2"]["anchor_span_recall"] == 0
    assert evidence_metrics((gold[0],), [candidate("a", 10, 20, page=2)], (1,))["metrics"]["1"]["anchor_span_recall"] == 0
    assert evidence_metrics((gold[0],), [hits[0], hits[0]], (2,))["metrics"]["2"]["anchor_span_recall"] == 0


@pytest.mark.parametrize("vectors", [[[0., 0.]], [[float('nan'), 1.]], [[float('inf'), 1.]], [[True, 1.]], [[1.]], []])
def test_invalid_vectors_fail_closed(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors, 1, 2)


def test_remote_budget_and_no_retry():
    model = PilotEmbedding(api_key="unit-test-secret", model="test", max_calls=1)
    requests = []
    def answer(request):
        requests.append(request)
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            model._post(client, ["synthetic"])
        with pytest.raises(BudgetExceeded):
            model._post(client, ["synthetic"])
    assert len(requests) == 1 and len(model.calls) == 1
    assert model.calls[0]["status"] == "failed"
    assert "unit-test-secret" not in json.dumps(model.calls)


def test_committed_questions_have_expected_mix():
    path = Path(__file__).resolve().parents[1] / "evaluation" / "literature_pilot_v1.json"
    pilot = Pilot.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(pilot.papers) == 3 and len(pilot.questions) == 20
    assert pilot.annotation_status == "ai_draft"
    assert {kind: sum(q.category == kind for q in pilot.questions) for kind in
        ["fact", "comparison", "multihop", "unanswerable"]} == {
            "fact": 8, "comparison": 6, "multihop": 2, "unanswerable": 4}


def test_traversal_and_dangling_labels_rejected(pilot):
    with pytest.raises(ValidationError):
        Paper.model_validate({**pilot.papers[0].model_dump(), "file_name": "../paper.pdf"})
    data = pilot.model_dump()
    data["questions"][0]["evidence"][0]["document_id"] = "other"
    with pytest.raises(ValidationError):
        Pilot.model_validate(data)
