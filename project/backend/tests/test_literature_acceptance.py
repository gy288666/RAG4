"""Acceptance tests use explicit synthetic judgments, never human gold labels."""
import hashlib
import json

import fitz
import pytest
from pydantic import ValidationError

from app.evaluation.acceptance import Review, Submission, prepare, score
from scripts.evaluate_literature_acceptance import main


@pytest.fixture
def frozen(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Source evidence is present on this page.")
        pdf.save(pdf_path)
    pilot = {"schema_version": "literature-pilot-v1", "corpus_version": "synthetic-v1",
             "annotation_status": "ai_draft", "papers": [{"document_id": "p", "title": "Synthetic",
                 "url": "https://example.invalid/p", "pdf_url": "https://example.invalid/p.pdf",
                 "file_name": "paper.pdf", "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                 "pages": 1, "license": "self-authored", "license_url": "https://example.invalid/license"}],
             "questions": [{"id": f"q{i+1:02}", "category": category, "question": "Test?",
                 "expected_answer": "Development draft", "evidence": [] if category == "unanswerable" else
                 [{"document_id": "p", "page": 1, "anchor": "Source evidence"}]}
                 for i, category in enumerate(["fact"] * 8 + ["comparison"] * 6 + ["multihop"] * 2 + ["unanswerable"] * 4)]}
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(json.dumps(pilot), encoding="utf-8")
    data = {"schema_version": "literature-answers-v1", "pilot_sha256": hashlib.sha256(pilot_path.read_bytes()).hexdigest(),
            "run_id": "synthetic-test-only", "answers": [{"question_id": q["id"], "text": "Test answer",
                "abstained": q["category"] == "unanswerable", "artifact_id": "synthetic-artifact",
                "artifact_sha256": "0" * 64, "claims": [] if q["category"] == "unanswerable" else
                [{"id": "c1", "text": "Evidence exists", "citations": [{"document_id": "p", "page": 1,
                    "quote": "Source evidence"}]}]} for q in pilot["questions"]]}
    return pilot_path, data


def build(frozen):
    path, data = frozen
    return prepare(path, path.parent, Submission.model_validate(data))


def reviewed(pack, template):
    data = template.model_dump(mode="json")
    data.update(reviewer="synthetic-reviewer-for-unit-tests", reviewed_at="2026-11-10T12:00:00Z",
                independent_human_attested=True)
    for j in data["judgments"]:
        j.update(answer_correct=True, gap_correct=True, reason="Synthetic test judgment")
        j["claim_support"] = {key: True for key in j["claim_support"]}
    return data


def test_pending_never_passes_and_complete_synthetic_review_passes(frozen):
    pack, template = build(frozen)
    assert score(pack, template)["status"] == "incomplete"
    result = score(pack, Review.model_validate(reviewed(pack, template)))
    assert result["subgate_passed"] and result["total_claims"] == 16
    assert result["correct_gaps"] == 4 and result["held_out_evaluation"] is False
    assert result["quality_gate_passed"] is False  # Not the full product gate.


def test_exact_threshold_and_gap_requirement(frozen):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["judgments"][0]["claim_support"]["c1"] = False
    assert score(pack, Review.model_validate(data))["subgate_passed"]  # 15/16
    data["judgments"][1]["claim_support"]["c1"] = False
    assert score(pack, Review.model_validate(data))["status"] == "failed"  # 14/16
    data = reviewed(pack, template)
    data["judgments"][-1]["gap_correct"] = False
    assert not score(pack, Review.model_validate(data))["subgate_passed"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "claim", "digest"])
def test_foreign_incomplete_or_mutated_reviews_rejected(frozen, mutation):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    if mutation == "missing": data["judgments"].pop()
    if mutation == "duplicate": data["judgments"][-1] = data["judgments"][0]
    if mutation == "unknown": data["judgments"][-1]["question_id"] = "foreign"
    if mutation == "claim": data["judgments"][0]["claim_support"] = {"foreign": True}
    if mutation == "digest": pack["submission"]["answers"][0]["text"] = "changed"
    with pytest.raises(ValueError): score(pack, Review.model_validate(data))


@pytest.mark.parametrize("field,value", [("independent_human_attested", False), ("reviewer", " "), ("reviewed_at", "")])
def test_unattested_review_cannot_pass(frozen, field, value):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data[field] = value
    assert score(pack, Review.model_validate(data))["status"] == "incomplete"


def test_all_abstention_and_empty_submission_cannot_pass(frozen):
    path, data = frozen
    for a in data["answers"]: a.update(abstained=True, claims=[])
    pack, template = build(frozen)
    result = score(pack, Review.model_validate(reviewed(pack, template)))
    assert result["status"] == "failed" and len(result["answerable_abstentions"]) == 16
    pack, template = prepare(path, path.parent)
    result = score(pack, template)
    assert len(result["missing_answers"]) == 20 and result["citation_support_rate"] is None


@pytest.mark.parametrize("mutation", ["page", "quote", "source", "pilot", "duplicate", "unknown"])
def test_bad_submission_rejected(frozen, mutation):
    path, data = frozen
    cite = data["answers"][0]["claims"][0]["citations"][0]
    if mutation == "page": cite["page"] = 2
    if mutation == "quote": cite["quote"] = "This was never in the paper"
    if mutation == "source": (path.parent / "paper.pdf").write_bytes(b"changed")
    if mutation == "pilot": data["pilot_sha256"] = "f" * 64
    if mutation == "duplicate": data["answers"].append(data["answers"][0])
    if mutation == "unknown": data["answers"][0]["question_id"] = "foreign"
    with pytest.raises(ValueError): build(frozen)


def test_boolean_strings_not_accepted(frozen):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["judgments"][0]["claim_support"]["c1"] = "true"
    with pytest.raises(ValidationError): Review.model_validate(data)


def test_missing_judgment_is_pending_and_cli_preserves_existing_output(frozen, tmp_path):
    path, _ = frozen
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["judgments"][0]["claim_support"]["c1"] = None
    assert score(pack, Review.model_validate(data))["status"] == "incomplete"
    output = tmp_path / "out"
    args = ["--pilot", str(path), "--sources", str(path.parent), "--output", str(output)]
    assert main(args) == 2
    before = (output / "report.json").read_bytes()
    with pytest.raises(FileExistsError): main(args)
    assert (output / "report.json").read_bytes() == before


def test_cli_complete_review_is_bound_to_answers_and_sources(frozen, tmp_path):
    path, answers = frozen
    pack, template = build(frozen)
    answers_path, review_path = tmp_path / "answers.json", tmp_path / "review.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")
    review_path.write_text(json.dumps(reviewed(pack, template)), encoding="utf-8")
    args = ["--pilot", str(path), "--sources", str(path.parent), "--answers", str(answers_path),
            "--review", str(review_path), "--output", str(tmp_path / "scored")]
    assert main(args) == 0
    answers["answers"][0]["text"] = "A different answer"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")
    args[-1] = str(tmp_path / "changed")
    with pytest.raises(ValueError, match="frozen pack"): main(args)
    assert not (tmp_path / "changed").exists()


@pytest.mark.parametrize("value", ["2026-11-10", "not-a-time"])
def test_review_timestamp_must_be_real_and_timezone_aware(frozen, value):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["reviewed_at"] = value
    with pytest.raises(ValueError): Review.model_validate(data)


def test_blank_review_reason_is_pending(frozen):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["judgments"][0]["reason"] = " "
    assert score(pack, Review.model_validate(data))["status"] == "incomplete"


def test_reviewed_wrong_answer_cannot_pass_on_good_citations_alone(frozen):
    pack, template = build(frozen)
    data = reviewed(pack, template)
    data["judgments"][0]["answer_correct"] = False
    result = score(pack, Review.model_validate(data))
    assert result["citation_support_rate"] == 1
    assert result["status"] == "failed" and not result["subgate_passed"]
