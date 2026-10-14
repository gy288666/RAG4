"""Real-paper Phase 1–5 development pilot in a fresh isolated SQLite database.

Reuses exactly matched, previously recorded document embeddings; new research
queries and all claims/judgments use the live model. No business DB or credentials
are written. This is a development pilot, not an independent quality holdout.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import httpx
from time import perf_counter
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--cached-run", type=Path, required=True)
    parser.add_argument("--cached-report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-30B-A3B-Instruct-2507")
    parser.add_argument("--model-timeout", type=int, default=60, choices=range(1, 61))
    parser.add_argument("--extraction-protocol", choices=("literal-quote-v1", "source-handles-v2"), default="source-handles-v2")
    parser.add_argument("--response-format", choices=("text", "json_object"), default="json_object")
    parser.add_argument("--retry-network-once", action="store_true",
        help="Explicitly resume at most one failed network step; consumes task/call budgets")
    args = parser.parse_args()
    key = os.environ.get("RAG4_EVAL_API_KEY")
    if not key:
        parser.error("Set RAG4_EVAL_API_KEY in memory; never pass it on the command line")
    cached_report = args.cached_run / "report.json"
    if hashlib.sha256(cached_report.read_bytes()).hexdigest() != args.cached_report_sha256:
        parser.error("Cached report digest mismatch")
    previous = json.loads(cached_report.read_text(encoding="utf-8"))
    if previous["status"] != "succeeded" or previous["config"]["dimension"] != 4096:
        parser.error("A successful 4096-dimensional retrieval run is required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Set isolated configuration BEFORE importing any application SQL module.
    os.environ["ENV_FILE"] = str(output / "nonexistent.env")
    os.environ["DATABASE_URL"] = "sqlite:///" + (output / "research.sqlite").as_posix()
    os.environ["DEV_MOCK_AI"] = "false"
    os.environ["UPLOAD_DIR"] = str(output / "uploads")
    os.environ["CHROMA_DIR"] = str(output / "vectors")
    from app.core.database import init_db, session_scope
    from app.evaluation.literature import Pilot, load_documents
    from app.models.document import Document
    from app.models.user import User
    from app.research.agent import ResearchAgent
    from app.research.evidence import HybridEvidenceEngine
    from app.research.graph import MemoryGraphStore
    from app.research.model import CompletionSpec, JsonResearchModel
    from app.research.runtime import FrozenVersionRetriever, _load_scope, create_task
    from app.research.store import SQLResearchTaskStore
    from app.research.tasks import TaskBudget
    from app.research.tools import ToolContext
    from app.services import index_job_service as jobs, index_build_service as builds, index_version_service as versions
    from app.chunking import ChunkingConfig
    from app.services.vector_store import LocalVectorStore
    from app.services.vector_store import records_digest
    from evaluate_literature import PilotEmbedding

    report = {"schema_version": "research-comparison-result-v1", "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(), "annotation_status": "machine_review_only",
        "cached_report_sha256": args.cached_report_sha256,
        "network": {"siliconflow_no_proxy": "api.siliconflow.cn" in os.environ.get("NO_PROXY", "")},
        "network_retry_limit": int(args.retry_network_once), "retry_events": [],
        "cached_embeddings": "reused document vectors, exact chunk ID/text match; no document embedding API calls",
        "steps": [], "activation_rehearsal": [], "error_type": None,
        "limitations": ["SQLite experiment, not a MySQL production deployment", "No human citation support audit",
            "Development corpus, not independent training holdout", "Model judgments are fallible; no comparable performance ranking",
            "Graph relations are source-backed hypotheses, not certified semantic facts"], "cost": "unknown"}
    started = perf_counter()
    tasks, task, embedding, model, client = SQLResearchTaskStore(), None, None, None, None
    store = LocalVectorStore(str(output / "vectors"))
    backend = Path(__file__).resolve().parents[1]
    code_files = sorted((backend / "app/research").glob("*.py")) + [Path(__file__).resolve(), backend / "app/services/index_version_service.py"]
    report["executed_source_sha256"] = {str(p.relative_to(backend)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_files}

    def save():
        report["duration_ms"] = round((perf_counter() - started) * 1000)
        report["embedding_calls"] = embedding.calls if embedding else []
        report["completion_calls"] = model.calls if model else []
        if task:
            report["task_id"], report["task_status"] = task.id, task.status
            report["model_calls_reserved"], report["tool_calls_used"] = task.model_calls_used, task.tool_calls_used
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        pilot = Pilot.model_validate_json(args.pilot.read_text(encoding="utf-8"))
        load_documents(pilot, args.sources)  # Verify PDF bytes/page counts before any model use.
        if [p.model_dump() for p in pilot.papers] != previous["sources"]:
            raise ValueError("Cached source manifest mismatch")
        report["sources"] = [p.model_dump() for p in pilot.papers]
        report["pilot_sha256"] = hashlib.sha256(pilot.model_dump_json().encode()).hexdigest()
        cached_store = LocalVectorStore(str(args.cached_run / "vectors"))
        cached = cached_store.read_records(1, index_version="rag4")
        report["cached_vectors_sha256"] = records_digest(cached)
        report["cached_vector_file_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (args.cached_run / "vectors").glob("*.json") if "rag4" in p.name}
        report["limitations"].append("Previous retrieval report did not seal raw vector values; cache digest frozen at this execution")
        wanted = json.loads((args.cached_run / "rag4-chunks.json").read_text(encoding="utf-8"))
        if {r.id: (r.text, r.doc_id, r.chunk_index) for r in cached} != {c["id"]: (c["text"], c["document_id"], c["index"]) for c in wanted}:
            raise ValueError("Cached vector provenance mismatch")
        init_db()
        with session_scope() as db:
            db.add(User(id=1, email="pilot@example.invalid", password_hash="not-a-login", status=1))
            for paper in pilot.papers:
                db.add(Document(id=paper.document_id, user_id=1, file_name=paper.file_name, status="ready",
                    local_path=str((args.sources / paper.file_name).resolve()), file_size=(args.sources / paper.file_name).stat().st_size))
        cache_by_text = {}
        for record in cached:
            if record.text in cache_by_text and cache_by_text[record.text] != record.embedding:
                raise ValueError("Ambiguous cached document vector")
            cache_by_text[record.text] = record.embedding

        class CachedEmbedding:
            def __init__(self, **kwargs):
                pass
            def embed_documents(self, texts):
                return [cache_by_text[text] for text in texts]

        build_spec = builds.EmbeddingSpec(endpoint="https://api.siliconflow.cn/v1/embeddings",
            model_id=previous["model"]["model_id"], version=previous["model"]["version"], dimension=4096)
        builds.RemoteEmbeddingAdapter = CachedEmbedding  # Isolated evaluation process only.
        build_ids, identities = [], []
        for paper in pilot.papers:
            job = jobs.run_job(1, jobs.create_job(1, paper.document_id, idempotency_key="prepare:" + paper.document_id,
                config=ChunkingConfig(child_max_tokens=600, parent_max_tokens=1800)).id)
            if job.status != "succeeded":
                raise ValueError("Pilot chunk preparation failed")
            chunks = jobs.load_chunk_set(1, job.chunk_set_id)
            if {c.chunk_id for c in chunks.child_chunks} != {r.id for r in cached if r.doc_id == paper.document_id}:
                raise ValueError("Chunk identities changed; cached vectors cannot be reused")
            build = builds.create_build(1, chunks.chunk_set_id, build_spec, idempotency_key="build:" + paper.document_id)
            built = builds.run_build(1, build.id, api_key="not-used-by-cache", store=store)
            if built.status != "validated":
                raise ValueError("Pilot candidate validation failed")
            build_ids.append(build.id)
            identities.append({"document_id": paper.document_id, "chunk_set_id": chunks.chunk_set_id,
                "parser_version": chunks.parser_version, "chunking_version": chunks.chunking_version})
        report["chunk_sets"] = identities
        version = versions.create_version(1, build_ids, store=store)
        # Exercise real Phase 2 SQL CAS + all-vector readback with real sources,
        # inside the new experiment DB. The business active pointer is untouched.
        report["activation_rehearsal"].append(versions.switch_version(1, version.id, expected_revision=0, store=store))
        second = versions.create_version(1, build_ids, store=store)
        report["activation_rehearsal"].append(versions.switch_version(1, second.id, expected_revision=1, store=store))
        report["activation_rehearsal"].append(versions.switch_version(1, version.id, expected_revision=2, store=store))
        report["activation_rehearsal"].append(versions.switch_version(1, None, expected_revision=3, store=store))
        completion = CompletionSpec(endpoint="https://api.siliconflow.cn/v1/chat/completions", model_id=args.model,
            timeout_seconds=args.model_timeout, max_output_tokens=2048,
            extraction_protocol=args.extraction_protocol, response_format=args.response_format)
        client = httpx.Client(timeout=httpx.Timeout(args.model_timeout, connect=8), limits=httpx.Limits(keepalive_expiry=60))
        report["network"]["caller_owned_connection_reuse"] = True
        model = JsonResearchModel(completion, api_key=key, max_calls=8, client=client)
        embedding = PilotEmbedding(api_key=key, model=build_spec.model_id, max_calls=4, client=client)
        report["completion_spec"], report["embedding_spec"] = completion.model_dump(), build_spec.model_dump()
        task = create_task(1, version.id, tuple(p.document_id for p in pilot.papers),
            "比较三篇论文的方法、数据集、结果和局限，注明实验条件；证据不足明确列出，禁止直接性能排名。",
            completion=completion, budget=TaskBudget(), vector_store=store, task_store=tasks)

        def context_factory(current):
            def fresh():
                corpus, bindings, manifest = _load_scope(1, version.id, tuple(p.document_id for p in pilot.papers), store)
                if corpus.corpus_id != current.corpus_id or bindings != current.sources:
                    raise ValueError("Source drift")
                return corpus, manifest
            corpus, manifest = fresh()
            graph = MemoryGraphStore()
            for p in pilot.papers:
                graph.replace_document(1, p.document_id, tuple(r for r in current.relations if r.document_id == p.document_id), corpus)
            retriever = FrozenVersionRetriever(current, corpus, manifest, SimpleNamespace(
                embedding_base_url="https://api.siliconflow.cn/v1", embedding_api_key=key), store, model=embedding, research_facets=True)
            return ToolContext(current, corpus, HybridEvidenceEngine(corpus, retriever, graph), model, fresh)

        agent = ResearchAgent(tasks, context_factory)
        save()
        for _ in range(task.budget.max_steps):
            task = agent.step(1, task.id)
            report["steps"] = [s.model_dump(mode="json") for s in task.steps]
            save()
            print(json.dumps({"status": task.status, "tools": task.tool_calls_used, "error_code": task.error_code}), flush=True)
            failed_calls = [c for c in embedding.calls + model.calls if c.get("status") == "failed"]
            if (task.status == "failed" and args.retry_network_once and not report["retry_events"]
                    and failed_calls and failed_calls[-1].get("error_type") in {"ConnectError", "ReadTimeout", "ConnectTimeout"}):
                report["retry_events"].append({"revision": task.revision, "error_type": failed_calls[-1]["error_type"]})
                task = agent.control(1, task.id, "resume", task.revision)
                save()
                continue
            if task.status in {"completed", "failed", "paused", "cancelled"}:
                break
        (output / "task.json").write_text(task.model_dump_json(indent=2), encoding="utf-8")
        report["status"] = "succeeded" if task.status == "completed" else "failed"
        if task.artifact:
            (output / "comparison.md").write_text(task.artifact.markdown, encoding="utf-8")
            (output / "artifact.json").write_text(task.artifact.model_dump_json(indent=2), encoding="utf-8")
            report["artifact_id"] = task.artifact.artifact_id
            report["verification"] = task.verification.model_dump(mode="json")
            report["cells"] = [r.model_dump(mode="json") for r in task.artifact.rows]
            report["knowledge_gaps"] = task.artifact.knowledge_gaps
            report["graph_relation_count"] = len(task.relations)
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
    finally:
        save()
        if client is not None:
            client.close()
    print(json.dumps({"status": report["status"], "output": str(output), "error_type": report["error_type"]}), flush=True)
    return 0 if report["status"] == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
