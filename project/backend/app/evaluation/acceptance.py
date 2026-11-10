"""Offline, source-bound review of the 20-question development pilot.

Human independence is an explicit reviewer attestation, not something this
module can authenticate. A passed development pilot is never a held-out eval.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import unicodedata

from pydantic import Field, StrictBool, model_validator

from app.evaluation.literature import Label, Pilot, load_documents, locate_evidence


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


class Citation(Label):
    document_id: str = Field(min_length=1)
    page: int = Field(strict=True, gt=0)
    quote: str = Field(min_length=3)


class Claim(Label):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    citations: tuple[Citation, ...] = Field(min_length=1)


class Answer(Label):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    abstained: bool = Field(strict=True)
    claims: tuple[Claim, ...] = ()
    artifact_id: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_claims(self):
        if len({c.id for c in self.claims}) != len(self.claims):
            raise ValueError("Duplicate claim ID")
        if self.abstained and self.claims:
            raise ValueError("Abstention cannot publish factual claims")
        if not self.abstained and not self.claims:
            raise ValueError("An answer requires cited claims")
        if not self.text.strip() or any(not c.text.strip() for c in self.claims):
            raise ValueError("Blank answer or claim")
        return self


class Submission(Label):
    schema_version: str = Field(pattern=r"^literature-answers-v1$")
    pilot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    answers: tuple[Answer, ...]


class Judgment(Label):
    question_id: str
    # null is deliberately pending, never an implicit negative or success.
    answer_correct: bool | None = Field(default=None, strict=True)
    gap_correct: bool | None = Field(default=None, strict=True)
    claim_support: dict[str, StrictBool | None] = Field(default_factory=dict)
    reason: str = ""


class Review(Label):
    pack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = ""
    reviewed_at: str = ""
    independent_human_attested: bool = Field(default=False, strict=True)
    judgments: tuple[Judgment, ...]

    @model_validator(mode="after")
    def check_timestamp(self):
        if self.reviewed_at:
            stamp = datetime.fromisoformat(self.reviewed_at.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Review timestamp requires a timezone")
        return self


def prepare(pilot_path: Path, sources: Path, submission: Submission | None = None):
    """Verify actual PDFs/anchors before freezing inputs; no DB or network calls."""
    pilot_bytes = pilot_path.read_bytes()
    pilot = Pilot.model_validate_json(pilot_bytes)
    if Counter(q.category for q in pilot.questions) != {
        "fact": 8, "comparison": 6, "multihop": 2, "unanswerable": 4
    }:
        raise ValueError("Acceptance requires the planned 8/6/2/4 question distribution")
    documents = load_documents(pilot, sources)
    locate_evidence(pilot, documents)
    pilot_sha = hashlib.sha256(pilot_bytes).hexdigest()
    answers = {} if submission is None else {a.question_id: a for a in submission.answers}
    if submission is not None:
        if submission.pilot_sha256 != pilot_sha:
            raise ValueError("Submission pilot digest mismatch")
        if len(answers) != len(submission.answers) or set(answers) - {q.id for q in pilot.questions}:
            raise ValueError("Duplicate or unknown answer question ID")
    normalized = lambda value: " ".join(unicodedata.normalize("NFKC", value).split())
    for answer in answers.values():
        for claim in answer.claims:
            for citation in claim.citations:
                document = documents.get(citation.document_id)
                pages = [] if document is None else [b.text for b in document.blocks if b.page == citation.page]
                quote = normalized(citation.quote)
                if len(quote) < 3 or not any(quote in normalized(page) for page in pages):
                    raise ValueError("Citation quote not found on declared source page")
    pack = {"schema_version": "literature-acceptance-pack-v1", "pilot_sha256": pilot_sha,
            "pilot": pilot.model_dump(mode="json"),
            "parsed_sha256": {key: digest([(b.page, b.text) for b in doc.blocks])
                              for key, doc in documents.items()},
            "executed_source_sha256": {name: hashlib.sha256(
                (Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
                for name in ("app/evaluation/acceptance.py", "app/evaluation/literature.py",
                             "app/services/parser_service.py", "scripts/evaluate_literature_acceptance.py")},
            "submission": None if submission is None else submission.model_dump(mode="json")}
    review = Review(pack_sha256=digest(pack), judgments=tuple(
        Judgment(question_id=q.id, claim_support={c.id: None for c in answers[q.id].claims}
                 if q.id in answers else {}) for q in pilot.questions))
    return pack, review


def score(pack: dict, review: Review) -> dict:
    """Fail closed on incomplete/foreign reviews; report counts without rounding gates."""
    if review.pack_sha256 != digest(pack):
        raise ValueError("Review does not match frozen pack")
    pilot = Pilot.model_validate(pack["pilot"])
    submission = None if pack["submission"] is None else Submission.model_validate(pack["submission"])
    answers = {} if submission is None else {a.question_id: a for a in submission.answers}
    judgments = {j.question_id: j for j in review.judgments}
    if len(judgments) != len(review.judgments) or set(judgments) != {q.id for q in pilot.questions}:
        raise ValueError("Review must contain every question exactly once")
    supported = total = gaps = reviewed = correct = 0
    missing, pending, abstentions = [], [], []
    for q in pilot.questions:
        answer, judgment = answers.get(q.id), judgments[q.id]
        expected_ids = set() if answer is None else {c.id for c in answer.claims}
        if set(judgment.claim_support) != expected_ids:
            raise ValueError("Review claim IDs differ from frozen answer")
        if answer is None:
            missing.append(q.id)
            continue
        total += len(answer.claims)
        supported += sum(v is True for v in judgment.claim_support.values())
        complete = (judgment.answer_correct is not None and bool(judgment.reason.strip())
                    and all(v is not None for v in judgment.claim_support.values()))
        if q.category == "unanswerable":
            complete = complete and judgment.gap_correct is not None
            gaps += int(answer.abstained and judgment.gap_correct is True and judgment.answer_correct is True)
        elif answer.abstained:
            abstentions.append(q.id)
        if complete:
            reviewed += 1
            correct += int(judgment.answer_correct is True)
        else:
            pending.append(q.id)
    independent = (review.independent_human_attested and bool(review.reviewer.strip())
                   and bool(review.reviewed_at.strip()))
    ready = not missing and not pending and independent
    passed = (ready and correct == len(pilot.questions) and not abstentions
              and total > 0 and supported * 10 >= total * 9 and gaps == 4)
    return {"schema_version": "literature-acceptance-result-v1", "pack_sha256": digest(pack),
            "status": "passed" if passed else "failed" if ready else "incomplete",
            "scope": "citation-and-gap-subgate", "subgate_passed": passed,
            "quality_gate_passed": False, "questions": len(pilot.questions),
            "answered": len(answers), "reviewed": reviewed, "answers_correct": correct,
            "supported_claims": supported, "total_claims": total,
            "citation_support_rate": supported / total if total else None,
            "correct_gaps": gaps, "required_gaps": 4, "missing_answers": missing,
            "pending_reviews": pending, "answerable_abstentions": abstentions,
            "independent_human_attested": independent, "held_out_evaluation": False,
            "remaining_product_gates": ["Three-paper comparison artifact coverage",
                                        "Matched RAG3 comparison: two fixed cross-paper failures, no regression",
                                        "Frozen runtime budgets and usage/latency accounting"],
            "limitations": ["Reviewer independence is declared, not authenticated",
                            "Quote presence does not prove semantic support",
                            "AI-draft labels and reused questions remain a development set",
                            "Artifact hashes are declared provenance; original exports must be audited"]}
