"""Paired answer generation from sealed retrieval hits; no SQL, labels or retries.

This isolates the two historical chunking policies, not the full ResearchAgent.
Raw prose uses the existing RAG prompt; claims/abstention are NOT guessed from it.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.literature import Pilot, load_documents, make_candidates
from app.services.prompts import RAG_SYSTEM_PROMPT, build_context_block

ENDPOINT = "https://api.siliconflow.cn/v1/chat/completions"
POLICY = {"completion_limit": 40, "timeout_seconds": 30, "wall_budget_seconds": 600,
          "max_tokens": 4096, "temperature": 0.2, "attempts_per_answer": 1,
          "top_k": 10, "max_context_chars": 6000, "embedding_calls": 0,
          "reranker": False, "parent_expansion": False, "graph": False}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def freeze_inputs(pilot_path, sources, cached_report, report_sha, model_task, task_sha):
    """Validate every selected source before any provider request or output creation."""
    raw, task_raw = cached_report.read_bytes(), model_task.read_bytes()
    if sha(raw) != report_sha or sha(task_raw) != task_sha:
        raise ValueError("Frozen input digest mismatch")
    prior, task = json.loads(raw), json.loads(task_raw)
    spec = task["completion"]
    if spec["endpoint"] != ENDPOINT or not spec["model_id"].strip():
        raise ValueError("Unauthorized completion endpoint or empty model")
    pilot_raw = pilot_path.read_bytes()
    pilot = Pilot.model_validate_json(pilot_raw)
    if len(pilot.questions) != 20:
        raise ValueError("Expected the complete 20-question pilot")
    if (prior["status"] != "succeeded" or prior["corpus_version"] != pilot.corpus_version
            or prior["pilot_sha256"] != sha(pilot.model_dump_json().encode())):
        raise ValueError("Retrieval pilot mismatch")
    expected_config = {"rag3_size": 600, "rag3_overlap": 60, "rag4_child_budget": 600,
                       "rag4_parent_budget": 1800, "rag4_overlap": 0, "reranker": False}
    if any(prior["config"].get(k) != v for k, v in expected_config.items()):
        raise ValueError("Unexpected cached chunking policy")
    documents = load_documents(pilot, sources)
    candidates = make_candidates(documents, size=600, overlap=60, parent_size=1800)
    actual = {variant: {c.id: asdict(c) for c in chunks} for variant, chunks in candidates.items()}
    rows = {(r["question_id"], r["variant"]): r for r in prior["rows"]}
    keys = {(q.id, v) for q in pilot.questions for v in ("rag3", "rag4")}
    if len(rows) != len(prior["rows"]) or set(rows) != keys:
        raise ValueError("Missing, duplicate or foreign retrieval row")
    planned = []
    for index, question in enumerate(pilot.questions):
        # Counterbalance request order; no selecting successful questions first.
        for variant in (("rag3", "rag4") if index % 2 == 0 else ("rag4", "rag3")):
            row = rows[(question.id, variant)]
            hits = row["hits"][:POLICY["top_k"]]
            if len(hits) != POLICY["top_k"] or len({h["id"] for h in hits}) != len(hits):
                raise ValueError("Incomplete or repeated retrieval hits")
            for hit in hits:
                known = actual[variant].get(hit["id"])
                # JSON changes dataclass tuples to lists; compare canonical JSON.
                if known is None or json.dumps(known, sort_keys=True) != json.dumps(
                        {k: hit[k] for k in known}, sort_keys=True):
                    raise ValueError("Cached hit differs from current source chunk")
                if len(hit["spans"]) != 1 or hit["spans"][0]["page"] is None:
                    raise ValueError("Expected one PDF page per evidence item")
            if sum(len(h["text"]) for h in hits) > POLICY["max_context_chars"]:
                raise ValueError("Evidence context budget exceeded")
            evidence = [{"index": i, "document_id": h["document_id"], "chunk_id": h["id"],
                         "page": h["spans"][0]["page"], "text": h["text"], "spans": h["spans"]}
                        for i, h in enumerate(hits, 1)]
            context = build_context_block([f'[{e["index"]}] 《{e["document_id"]}.pdf》—— 第 {e["page"]} 页\n{e["text"]}'
                                           for e in evidence])
            messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT.format(retrieved_contexts=context)},
                        {"role": "user", "content": question.question}]
            planned.append({"question_id": question.id, "variant": variant,
                            "evidence": evidence, "messages": messages})
    backend = Path(__file__).resolve().parents[1]
    manifest = {"schema_version": "literature-paired-answers-v1", "scope": "chunking-policy-only",
                "pilot_sha256": sha(pilot_raw), "retrieval_report_sha256": report_sha,
                "model_task_sha256": task_sha, "model": spec["model_id"], "endpoint": ENDPOINT,
                "embedding": prior["model"], "policy": POLICY,
                "prompt_sha256": sha(RAG_SYSTEM_PROMPT.encode()),
                "parsed_sha256": {key: sha(json.dumps([(b.page, b.text) for b in doc.blocks],
                    ensure_ascii=False).encode()) for key, doc in documents.items()},
                "source_sha256": {p.document_id: p.sha256 for p in pilot.papers},
                "executed_source_sha256": {name: sha((backend / name).read_bytes()) for name in (
                    "scripts/evaluate_literature_answers.py", "app/evaluation/literature.py",
                    "app/services/prompts.py", "app/services/chunking_service.py", "app/services/parser_service.py",
                    "app/chunking/engine.py", "app/chunking/adapter.py", "app/chunking/models.py")},
                "planned_requests": planned,
                "limitations": ["Development questions, not held-out data",
                    "Chunk policies differ in overlap; no isolated parent-context benefit",
                    "Cached dense retrieval, no live upload/Reranker/Agent execution",
                    "Plain answers require explicit claim annotation before R55 scoring",
                    "Successful generation does not establish answer/citation correctness"]}
    return manifest


def run(manifest, output, key, *, client=None, clock=perf_counter, progress=print):
    """Persist frozen requests first and each outcome immediately; failures consume slots."""
    if not key:
        raise ValueError("Provider key required")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "manifest.json", manifest)
    report = {"schema_version": "literature-paired-answer-result-v1", "scope": manifest["scope"],
              "manifest_sha256": sha((output / "manifest.json").read_bytes()),
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "quality_gate_passed": False, "human_reviewed": 0, "cost": "unknown", "rows": []}
    started, failures, stop = clock(), 0, None
    owned = client is None
    if owned:
        client = httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False,
                              timeout=httpx.Timeout(POLICY["timeout_seconds"], connect=5))
    try:
        for slot, request in enumerate(manifest["planned_requests"]):
            entry = {"slot": slot, "question_id": request["question_id"], "variant": request["variant"],
                     "status": "not_attempted", "usage": {}, "answer": None,
                     "request_sha256": sha(json.dumps(request, ensure_ascii=False, sort_keys=True).encode())}
            report["rows"].append(entry)
            remaining = POLICY["wall_budget_seconds"] - (clock() - started)
            if stop is None and (slot >= POLICY["completion_limit"] or remaining <= 0):
                stop = "budget_exhausted"
            if stop:
                entry["reason"] = stop
                dump(output / "report.json", report)
                continue
            entry["status"] = "started"
            dump(output / "report.json", report)
            call_start = clock()
            try:
                response = client.post(ENDPOINT, headers={"Authorization": "Bearer " + key},
                    timeout=httpx.Timeout(min(POLICY["timeout_seconds"], remaining), connect=min(5, remaining)),
                    json={"model": manifest["model"], "messages": request["messages"], "stream": False,
                          "temperature": POLICY["temperature"], "max_tokens": POLICY["max_tokens"]})
                entry["http_status"] = response.status_code
                if response.status_code in (401, 403, 429):
                    stop = "provider_authorization_or_rate_limit"
                response.raise_for_status()
                body = response.json()
                usage = body.get("usage", {})
                if isinstance(usage, dict):
                    entry["usage"] = {k: v for k, v in usage.items() if k in
                        {"prompt_tokens", "completion_tokens", "total_tokens"} and type(v) is int and v >= 0}
                choice = body["choices"][0]
                content = choice["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Empty or non-text answer")
                entry.update(answer=content, finish_reason=choice.get("finish_reason"))
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Truncated answer")
                entry["status"] = "succeeded"
                failures = 0
            except Exception as error:
                entry.update(status="failed", error_type=type(error).__name__)
                failures += 1
                if failures >= 3 and stop is None:
                    stop = "three_consecutive_failures"
            finally:
                entry["elapsed_ms"] = round((clock() - call_start) * 1000)
                dump(output / "report.json", report)
            progress(json.dumps({k: entry[k] for k in ("slot", "question_id", "variant", "status", "elapsed_ms")}))
    finally:
        if owned:
            client.close()
        rows = report["rows"]
        report.update(status="completed" if len(rows) == 40 and all(r["status"] == "succeeded" for r in rows)
                      else "incomplete", elapsed_ms=round((clock() - started) * 1000),
                      attempted=sum(r["status"] != "not_attempted" for r in rows),
                      succeeded=sum(r["status"] == "succeeded" for r in rows),
                      stop_reason=stop, finished_at=datetime.now(timezone.utc).isoformat())
        report["reported_usage"] = {k: sum(r["usage"].get(k, 0) for r in rows)
                                    for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        report["usage_missing_rows"] = [r["slot"] for r in rows if r["status"] != "not_attempted" and not r["usage"]]
        dump(output / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pilot", "sources", "cached-report", "model-task", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("report-sha256", "task-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    manifest = freeze_inputs(args.pilot, args.sources, args.cached_report, args.report_sha256,
                             args.model_task, args.task_sha256)
    key = os.environ.get("RAG4_EVAL_API_KEY")
    if not key:
        keys = set(re.findall(r"sk-[A-Za-z0-9_-]{20,}", Path("E:/RAG3/提示.txt").read_text(encoding="utf-8-sig")))
        if len(keys) != 1:
            raise ValueError("Ambiguous provider key; set RAG4_EVAL_API_KEY")
        key = keys.pop()
    report = run(manifest, args.output, key)
    print(json.dumps({k: report[k] for k in ("status", "attempted", "succeeded", "elapsed_ms", "reported_usage")}))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
