"""One bounded live verification of a frozen research checkpoint.

Copies SQLite into a new output directory; never resumes or modifies the old
task or its active index. Requires RAG4_EVAL_API_KEY only in the environment.
This is a development comparison, not a human-labelled quality gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--claim-id", action="append", default=[], help="Optional explicit diagnostic subset; no new extraction")
    parser.add_argument("--protocol", choices=("source-checks-v3", "source-handles-v4"), default="source-checks-v3")
    args = parser.parse_args()
    key = os.environ["RAG4_EVAL_API_KEY"]
    args.output.mkdir(parents=True, exist_ok=False)
    target = args.output.resolve() / "snapshot.sqlite"
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(target) as copy:
        source.backup(copy)
    os.environ["ENV_FILE"] = str(args.output.resolve() / "nonexistent.env")
    os.environ["DATABASE_URL"] = "sqlite:///" + target.as_posix()
    os.environ["DEV_MOCK_AI"] = "false"
    from app.research.tasks import ResearchTask
    from app.research.runtime import _load_scope
    from app.research.model import JsonResearchModel
    from app.research.artifacts import EvidenceVerifier, ArtifactComposer
    from app.services.vector_store import LocalVectorStore
    task = ResearchTask.model_validate_json(args.task.read_text(encoding="utf-8"))
    requested = set(args.claim_id)
    if len(requested) != len(args.claim_id) or not requested <= {c.claim_id for c in task.claims}:
        raise ValueError("Invalid diagnostic claim scope")
    claims = tuple(c for c in task.claims if not requested or c.claim_id in requested)
    corpus, bindings, _ = _load_scope(task.user_id, task.index_version_id,
        tuple(s.document_id for s in task.sources), LocalVectorStore(str(args.vectors)))
    if corpus.corpus_id != task.corpus_id or bindings != task.sources:
        raise ValueError("Source snapshot mismatch")
    spec = task.completion.model_copy(update={"verification_protocol": args.protocol, "max_output_tokens": 8192})
    model = JsonResearchModel(spec, api_key=key, max_calls=1)
    report = {"schema": "research-source-checks-replay-v1", "annotation_status": "machine_review_only",
        "quality_gate_passed": False, "business_database_modified": False, "max_model_calls": 1,
        "source_task_sha256": hashlib.sha256(args.task.read_bytes()).hexdigest(),
        "corpus_id": corpus.corpus_id, "completion": spec.model_dump(mode="json"),
        "claim_ids": [c.claim_id for c in claims], "diagnostic_subset": bool(requested),
        "old_verification": task.verification.model_dump(mode="json") if task.verification else None,
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__).resolve().parents[1] / "app/research").glob("*.py")}}
    try:
        verification = EvidenceVerifier(model).verify(corpus, claims)
        artifact = ArtifactComposer().compose(corpus, task.goal, tuple(s.document_id for s in task.sources),
            {s.document_id: s.title for s in task.sources}, claims, verification)
        report.update(status="succeeded", verification=verification.model_dump(mode="json"),
            artifact_id=artifact.artifact_id, knowledge_gaps=len(artifact.knowledge_gaps))
        (args.output / "artifact.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        (args.output / "comparison.md").write_text(artifact.markdown, encoding="utf-8")
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__,
            diagnostics=getattr(error, "diagnostics", ()))
    finally:
        report["calls"] = model.calls
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "requests": len(model.calls),
        "supported": report.get("verification", {}).get("supported")}))
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
