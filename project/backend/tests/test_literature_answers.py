"""Paired generation safeguards; all provider responses here are synthetic."""
from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace

import fitz
import httpx
import pytest

from app.evaluation.literature import Pilot, load_documents, make_candidates
from app.services.rag_service import build_context_prompt
from app.services.prompts import RAG_SYSTEM_PROMPT
from scripts.evaluate_literature_answers import ENDPOINT, freeze_inputs, run
from scripts.export_literature_answer_review import export_review, fenced
from app.evaluation.acceptance import Submission


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "paper.pdf"
    with fitz.open() as pdf:
        for i in range(12):
            pdf.new_page().insert_textbox(fitz.Rect(40, 40, 550, 790),
                (f"Synthetic evidence page {i+1}. Retrieval is not answer correctness. " * 22), fontsize=10)
        pdf.save(source)
    definition = {"schema_version": "literature-pilot-v1", "corpus_version": "synthetic-v1", "annotation_status": "ai_draft",
        "papers": [{"document_id": "paper", "title": "Synthetic", "url": "https://example.invalid/paper",
            "pdf_url": "https://example.invalid/paper.pdf", "file_name": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "pages": 12, "license": "self-authored",
            "license_url": "https://example.invalid/license"}],
        "questions": [{"id": f"q{i:02}", "category": "fact", "question": f"Question {i}?",
            "expected_answer": "SECRET_DEVELOPMENT_LABEL_NEVER_SEND", "evidence": [{"document_id": "paper", "page": 1,
                "anchor": "Synthetic evidence"}]} for i in range(1, 21)]}
    pilot_path = tmp_path / "pilot.json"
    write(pilot_path, definition)
    pilot = Pilot.model_validate(definition)
    chunks = make_candidates(load_documents(pilot, tmp_path))
    report = {"status": "succeeded", "corpus_version": pilot.corpus_version,
        "pilot_sha256": hashlib.sha256(pilot.model_dump_json().encode()).hexdigest(), "model": {"model_id": "fake-embedding"},
        "config": {"rag3_size": 600, "rag3_overlap": 60, "rag4_child_budget": 600,
                   "rag4_parent_budget": 1800, "rag4_overlap": 0, "reranker": False},
        "rows": [{"question_id": q.id, "variant": v, "hits": [{**asdict(c), "score": 1.0} for c in chunks[v][:10]]}
                 for q in pilot.questions for v in ("rag3", "rag4")]}
    cached, task = tmp_path / "report.json", tmp_path / "task.json"
    report_sha = write(cached, report)
    task_sha = write(task, {"completion": {"model_id": "synthetic-model", "endpoint": ENDPOINT}})
    return [pilot_path, tmp_path, cached, report_sha, task, task_sha]


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def success(request):
    return httpx.Response(200, json={"choices": [{"message": {"content": "Synthetic answer [1]."}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})


def test_freeze_has_40_counterbalanced_requests_no_label_leak_and_baseline_prompt_parity(inputs):
    manifest = freeze_inputs(*inputs)
    planned = manifest["planned_requests"]
    assert len(planned) == 40
    assert [(r["question_id"], r["variant"]) for r in planned[:4]] == [
        ("q01", "rag3"), ("q01", "rag4"), ("q02", "rag4"), ("q02", "rag3")]
    assert "SECRET_DEVELOPMENT_LABEL" not in json.dumps(manifest)
    for r in planned:
        chunks = [SimpleNamespace(page=e["page"], text=e["text"], file_name="paper.pdf", chunk_index=i)
                  for i, e in enumerate(r["evidence"])]
        assert r["messages"][0]["content"] == RAG_SYSTEM_PROMPT.format(retrieved_contexts=build_context_prompt(chunks))


@pytest.mark.parametrize("mutation", ["sha", "source", "text", "spans", "missing", "duplicate", "pilot", "endpoint"])
def test_changed_sources_and_frozen_inputs_rejected_before_requests(inputs, mutation):
    if mutation == "sha": inputs[3] = "0" * 64
    elif mutation == "source": (inputs[1] / "paper.pdf").write_bytes(b"changed")
    elif mutation == "endpoint":
        inputs[5] = write(inputs[4], {"completion": {"model_id": "test", "endpoint": "https://example.invalid"}})
    else:
        data = json.loads(inputs[2].read_text())
        if mutation == "text": data["rows"][0]["hits"][0]["text"] = "forged"
        if mutation == "spans": data["rows"][0]["hits"][0]["spans"][0]["page"] = 99
        if mutation == "missing": data["rows"].pop()
        if mutation == "duplicate": data["rows"].append(data["rows"][0])
        if mutation == "pilot": data["pilot_sha256"] = "0" * 64
        inputs[3] = write(inputs[2], data)
    with pytest.raises(ValueError): freeze_inputs(*inputs)


def test_success_persists_raw_answers_and_no_credentials(inputs, tmp_path):
    manifest = freeze_inputs(*inputs)
    output = tmp_path / "out"
    seen = []
    def respond(request):
        assert (output / "manifest.json").exists()
        assert json.loads((output / "report.json").read_text())["rows"][-1]["status"] == "started"
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer fake-private-key"
        return success(request)
    with client(respond) as http:
        result = run(manifest, output, "fake-private-key", client=http, progress=lambda _: None)
    assert result["status"] == "completed" and result["attempted"] == result["succeeded"] == len(seen) == 40
    assert result["reported_usage"]["total_tokens"] == 600
    assert not result["quality_gate_passed"] and result["human_reviewed"] == 0
    assert "fake-private-key" not in "".join(p.read_text(encoding="utf-8") for p in output.glob("*.json"))
    with pytest.raises(FileExistsError): run(manifest, output, "fake", client=None)


@pytest.mark.parametrize("mode", ["timeout", "truncated", "malformed", "empty"])
def test_failures_retained_no_retry_three_failure_stop(inputs, tmp_path, mode):
    manifest = freeze_inputs(*inputs)
    calls = []
    def respond(request):
        calls.append(request)
        if mode == "timeout": raise httpx.ReadTimeout("secret-error-never-persist", request=request)
        if mode == "malformed": return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"choices": [{"message": {"content": "" if mode == "empty" else "Partial answer"},
                                                    "finish_reason": "length"}]})
    with client(respond) as http:
        result = run(manifest, tmp_path / "out", "fake", client=http, progress=lambda _: None)
    assert result["attempted"] == len(calls) == 3 and result["succeeded"] == 0
    assert len(result["rows"]) == 40 and result["stop_reason"] == "three_consecutive_failures"
    assert "secret-error-never-persist" not in json.dumps(result)
    if mode == "truncated": assert result["rows"][0]["answer"] == "Partial answer"


@pytest.mark.parametrize("status", [401, 403, 429])
def test_provider_rejection_stops_without_retry(inputs, tmp_path, status):
    with client(lambda _: httpx.Response(status, text="private provider error")) as http:
        result = run(freeze_inputs(*inputs), tmp_path / "out", "fake", client=http, progress=lambda _: None)
    assert result["attempted"] == 1 and result["stop_reason"] == "provider_authorization_or_rate_limit"
    assert "private provider error" not in json.dumps(result)


def test_elapsed_budget_prevents_calls(inputs, tmp_path):
    # One initial clock read and then expiry before the first admission.
    ticks = iter([0] + [601] * 100)
    with client(lambda _: pytest.fail("Expired budget must not make any request")) as http:
        result = run(freeze_inputs(*inputs), tmp_path / "out", "fake", client=http,
                     clock=lambda: next(ticks), progress=lambda _: None)
    assert result["attempted"] == 0 and result["stop_reason"] == "budget_exhausted"


def test_review_export_preserves_originals_and_requires_explicit_annotation(inputs, tmp_path):
    source, output = tmp_path / "run", tmp_path / "review"
    with client(success) as http:
        run(freeze_inputs(*inputs), source, "fake", client=http, progress=lambda _: None)
    original = (source / "report.json").read_bytes()
    result = export_review(source, output)
    assert result["successful_answers"] == {"rag3": 20, "rag4": 20}
    assert len(list(output.glob("answer-*.json"))) == 40
    annotation = json.loads((output / "rag4-annotation-pending.json").read_text(encoding="utf-8"))
    assert annotation["answers"][0]["text"] == "Synthetic answer [1]."
    with pytest.raises(ValueError): Submission.model_validate(annotation)  # pending is not a scored answer
    artifact = (output / "answer-01.json").read_bytes()
    assert hashlib.sha256(artifact).hexdigest() == annotation["answers"][0]["artifact_sha256"]
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["annotation_status"] == "pending" and summary["answer_correctness"] == "unknown"
    assert summary["rows"][0]["answer"] == "Synthetic answer [1]."
    assert "text" not in summary["rows"][0]["input_evidence"][0]
    assert (source / "report.json").read_bytes() == original
    with pytest.raises(FileExistsError): export_review(source, output)


@pytest.mark.parametrize("mutation", ["request", "manifest", "running"])
def test_review_export_rejects_changed_or_running_run(inputs, tmp_path, mutation):
    source = tmp_path / "run"
    with client(success) as http:
        run(freeze_inputs(*inputs), source, "fake", client=http, progress=lambda _: None)
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    if mutation == "request": report["rows"][0]["request_sha256"] = "0" * 64
    if mutation == "running": report["status"] = "running"
    if mutation == "manifest": (source / "manifest.json").write_text("{}", encoding="utf-8")
    write(source / "report.json", report)
    with pytest.raises(ValueError): export_review(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_untrusted_answer_cannot_break_review_fence():
    rendered = fenced("```\n<script>untrusted</script>\n```")
    assert rendered.startswith("````text\n") and rendered.endswith("\n````")
