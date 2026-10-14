"""Regression replay: numeric gates + recorded model judgments, no API calls.

This does not constitute an independent or live semantic re-verification. Never
overwrites the original artifact or its SQL task record.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.adapter import adapt_parse_result
from app.evaluation.literature import Pilot, load_documents
from app.research.artifacts import ArtifactComposer, EvidenceVerifier
from app.research.evidence import EvidenceCorpus
from app.research.tasks import ResearchTask


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = ResearchTask.model_validate_json(args.task.read_text(encoding="utf-8"))
    if task.verification is None:
        parser.error("Recorded model judgments required")
    args.output.mkdir(parents=True, exist_ok=False)
    pilot = Pilot.model_validate_json(args.pilot.read_text(encoding="utf-8"))
    parsed = load_documents(pilot, args.sources)
    bindings = {s.document_id: s for s in task.sources}
    if set(bindings) != set(parsed):
        raise ValueError("Task scope mismatch")
    corpus = EvidenceCorpus(task.user_id, tuple(ChunkingEngine().split(adapt_parse_result(parsed[p.document_id],
        document_id=p.document_id, file_name=p.file_name), ChunkingConfig(child_max_tokens=600, parent_max_tokens=1800)) for p in pilot.papers))
    if corpus.corpus_id != task.corpus_id or any(corpus.chunk_sets[d].chunk_set_id != bindings[d].chunk_set_id for d in bindings):
        raise ValueError("Frozen corpus changed")
    verdicts = {v.claim_id: v for v in task.verification.verdicts}
    class RecordedJudge:
        def generate(self, operation, payload):
            return {"verdicts": [verdicts[c["claim_id"]].model_dump(mode="json") for c in payload["claims"]]}
    verified = EvidenceVerifier(RecordedJudge()).verify(corpus, task.claims)
    artifact = ArtifactComposer().compose(corpus, task.goal, tuple(s.document_id for s in task.sources),
        {s.document_id: s.title for s in task.sources}, task.claims, verified)
    report = {"schema_version": "verification-replay-v1", "status": "succeeded",
        "mode": "offline_numeric_gate_plus_recorded_model_judgments", "extra_model_calls": 0,
        "input_task_sha256": hashlib.sha256(args.task.read_bytes()).hexdigest(),
        "original_artifact_id": task.artifact.artifact_id if task.artifact else None,
        "original_verifier_version": task.verification.verifier_version,
        "original_supported": task.verification.supported, "verification": verified.model_dump(mode="json"),
        "artifact_id": artifact.artifact_id, "completion_status": artifact.completion_status,
        "knowledge_gaps": artifact.knowledge_gaps, "sources": [p.model_dump() for p in pilot.papers],
        "limitations": ["Reuses original semantic judgments; no independent support audit", "Human quality gate not passed"],
        "executed_source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).resolve().parents[1] / "app/research/artifacts.py")}}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "artifact.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    (args.output / "comparison.md").write_text(artifact.markdown, encoding="utf-8")
    print(json.dumps({"original_supported": task.verification.supported, "supported": verified.supported,
        "total": verified.total, "completion_status": artifact.completion_status}))


if __name__ == "__main__":
    main()
