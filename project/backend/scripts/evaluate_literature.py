"""Small real-PDF retrieval pilot; explicit inputs, fresh output, no SQL writes."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluation.literature import (Pilot, evidence_metrics, load_documents,
    locate_evidence, make_candidates, validate_vectors)
from app.modeling.adapters.embedding import RemoteEmbeddingAdapter
from app.services.vector_store import LocalVectorStore, VectorRecord


class BudgetExceeded(RuntimeError):
    pass


class _CallDeadline:
    """Preserve this adapter's deadline when using a caller-owned connection."""
    def __init__(self, client, timeout):
        self.client, self.timeout = client, timeout

    def post(self, *args, **kwargs):
        return self.client.post(*args, **kwargs, timeout=self.timeout)


class PilotEmbedding(RemoteEmbeddingAdapter):
    """No retries; record provider usage without logging payloads or credentials."""
    def __init__(self, *, api_key, model, max_calls=80, timeout=30, client=None):
        super().__init__(endpoint="https://api.siliconflow.cn/v1/embeddings", api_key=api_key,
                         model_id=model, version="pilot-remote-v1", timeout=timeout,
                         max_retries=1, batch_size=16)
        self.max_calls = max_calls
        self.calls = []
        self.client = client

    def _post(self, client, batch):
        if len(self.calls) >= self.max_calls:
            raise BudgetExceeded("Pilot request budget exhausted")
        entry = {"inputs": len(batch), "status": "started", "usage": None}
        self.calls.append(entry)
        started = perf_counter()
        try:
            target = _CallDeadline(self.client, self._timeout) if self.client is not None else client
            payload = super()._post(target, batch)
            entry["status"] = "succeeded"
            usage = payload.get("usage", {})
            entry["usage"] = {key: value for key, value in usage.items()
                if key in {"prompt_tokens", "total_tokens"} and type(value) is int} if isinstance(usage, dict) else None
            return payload
        except Exception as error:
            entry.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            entry["duration_ms"] = round((perf_counter() - started) * 1000)


def run(pilot, source_dir, output, model, *, dimension=4096, size=600, overlap=60, parent_size=1800, ks=(1, 5, 10)):
    """All artifacts live in a new experiment directory; failures remain visible."""
    if not ks or any(k <= 0 for k in ks) or dimension <= 0:
        raise ValueError("Invalid dimension or retrieval budget")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "literature-result-v1", "status": "running",
        "corpus_version": pilot.corpus_version, "annotation_status": pilot.annotation_status,
        "started_at": datetime.now(timezone.utc).isoformat(), "variants": {},
        "model": asdict(model.descriptor),
        "config": {"dimension": dimension, "rag3_size": size, "rag3_overlap": overlap,
            "rag4_child_budget": size, "rag4_parent_budget": parent_size, "rag4_overlap": 0,
            "counter": "unicode-codepoint-v1", "ks": list(ks), "store": "LocalVectorStore/cosine",
            "reranker": False, "llm_answers": False,
            "remote_call_limit": getattr(model, "max_calls", None),
            "remote_timeout_seconds": getattr(model, "_timeout", None),
            "attempts_per_batch": getattr(model, "_max_retries", None)},
        "limitations": ["AI labels require human review", "Flat PDF parser: no heading/layout extraction",
            "Chunking policy includes different overlap; no isolated parent-context effect",
            "Anchor coverage is not citation support or answer correctness",
            "Unanswerable labels are retained but abstention is not evaluated"],
        "failure_stage": None, "cost": "unknown", "rows": []}
    backend = Path(__file__).resolve().parents[1]
    source_files = ["app/evaluation/literature.py", "scripts/evaluate_literature.py",
        "app/services/parser_service.py", "app/services/chunking_service.py", "app/chunking/engine.py",
        "app/chunking/adapter.py", "app/chunking/models.py", "app/modeling/adapters/embedding.py",
        "app/services/vector_store.py"]
    report["executed_source_sha256"] = {name: hashlib.sha256((backend / name).read_bytes()).hexdigest()
        for name in source_files}
    report["pilot_sha256"] = hashlib.sha256(pilot.model_dump_json().encode()).hexdigest()
    started = perf_counter()
    stage = "source_validation"
    try:
        documents = load_documents(pilot, source_dir)
        gold = locate_evidence(pilot, documents)
        variants = make_candidates(documents, size=size, overlap=overlap, parent_size=parent_size)
        (output / "pilot.json").write_text(pilot.model_dump_json(indent=2), encoding="utf-8")
        report["sources"] = [p.model_dump() for p in pilot.papers]
        report["parser_versions"] = {key: result.parser_version for key, result in documents.items()}
        report["parsed_sha256"] = {key: hashlib.sha256(json.dumps(
            [(b.page, b.text) for b in result.blocks], ensure_ascii=False).encode()).hexdigest()
            for key, result in documents.items()}
        try:
            report["code_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[3], stderr=subprocess.DEVNULL).decode().strip()
            report["dirty_files"] = subprocess.check_output(["git", "diff", "--name-only"],
                cwd=Path(__file__).resolve().parents[3], stderr=subprocess.DEVNULL).decode().splitlines()
        except (OSError, subprocess.CalledProcessError):
            report["code_commit"] = "unknown"
        stage = "query_embedding"
        query_vectors = model.embed_documents([q.question for q in pilot.questions])
        validate_vectors(query_vectors, len(pilot.questions), dimension)
        for variant, chunks in variants.items():
            stage = variant + "_embedding"
            build_start = perf_counter()
            vectors = model.embed_documents([c.text for c in chunks])
            validate_vectors(vectors, len(chunks), dimension)
            store = LocalVectorStore(str(output / "vectors"))
            store.add(1, [VectorRecord(id=c.id, text=c.text, embedding=v, doc_id=c.document_id,
                user_id=1, file_name=c.document_id + ".pdf", chunk_index=c.index,
                page=c.spans[0].page) for c, v in zip(chunks, vectors)], index_version=variant)
            candidates = {(c.document_id, c.index): c for c in chunks}
            report["variants"][variant] = {"chunks": len(chunks),
                "max_chunk_characters": max(len(c.text) for c in chunks),
                "build_duration_ms": round((perf_counter() - build_start) * 1000)}
            (output / (variant + "-chunks.json")).write_text(
                json.dumps([asdict(c) for c in chunks], ensure_ascii=False), encoding="utf-8")
            stage = variant + "_retrieval"
            for question, vector in zip(pilot.questions, query_vectors):
                query_start = perf_counter()
                hits = store.search(1, vector, max(ks), index_version=variant)
                ranked = [candidates[(hit.doc_id, hit.chunk_index)] for hit in hits]
                row = {"question_id": question.id, "variant": variant, "category": question.category,
                    "duration_ms": round((perf_counter() - query_start) * 1000),
                    "gold_spans": [asdict(s) for s in gold[question.id]],
                    "hits": [{**asdict(c), "score": hit.score} for c, hit in zip(ranked, hits)],
                    **evidence_metrics(gold[question.id], ranked, ks)}
                report["rows"].append(row)
            scored = [row for row in report["rows"] if row["variant"] == variant and row["metrics"] is not None]
            report["variants"][variant]["scored_questions"] = len(scored)
            report["variants"][variant]["unanswerable_not_scored"] = len(pilot.questions) - len(scored)
            report["variants"][variant]["metrics"] = {str(k): {
                "mean_anchor_span_recall": sum(r["metrics"][str(k)]["anchor_span_recall"] for r in scored) / len(scored),
                "all_evidence_questions": sum(r["metrics"][str(k)]["all_evidence_covered"] for r in scored)
            } for k in ks} if scored else {}
        report["status"] = "succeeded"
    except Exception as error:
        report.update(status="failed", failure_stage=stage, error_type=type(error).__name__)
    finally:
        report["duration_ms"] = round((perf_counter() - started) * 1000)
        report["remote_calls"] = getattr(model, "calls", [])
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-Embedding-8B")
    parser.add_argument("--dimension", type=int, default=4096)
    args = parser.parse_args()
    key = os.getenv("RAG4_EVAL_API_KEY", "")
    if not key:
        print(json.dumps({"status": "rejected", "reason": "RAG4_EVAL_API_KEY_required"}))
        return 2
    pilot = Pilot.model_validate_json(args.pilot.read_text(encoding="utf-8"))
    report = run(pilot, args.sources, args.output,
                 PilotEmbedding(api_key=key, model=args.model), dimension=args.dimension)
    print(json.dumps({"status": report["status"], "failure_stage": report["failure_stage"],
        "duration_ms": report["duration_ms"], "variants": report["variants"]}, ensure_ascii=True))
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
