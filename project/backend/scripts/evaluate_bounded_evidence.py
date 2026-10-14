"""One-variable parent context replay with equal limits and fixed real hits."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.adapter import adapt_parse_result
from app.evaluation.literature import Candidate, Pilot, Span, evidence_metrics, load_documents, locate_evidence
from app.research.evidence import EvidenceCorpus, HybridEvidenceEngine, RetrievalOptions, VectorHit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--retrieval-report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=6000)
    args = parser.parse_args()
    if hashlib.sha256(args.retrieval_report.read_bytes()).hexdigest() != args.report_sha256:
        parser.error("Retrieval report digest mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    pilot = Pilot.model_validate_json(args.pilot.read_text(encoding="utf-8"))
    parsed = load_documents(pilot, args.sources)
    gold = locate_evidence(pilot, parsed)
    corpus = EvidenceCorpus(1, tuple(ChunkingEngine().split(adapt_parse_result(parsed[p.document_id],
        document_id=p.document_id, file_name=p.file_name), ChunkingConfig(child_max_tokens=600, parent_max_tokens=1800)) for p in pilot.papers))
    prior = json.loads(args.retrieval_report.read_text(encoding="utf-8"))
    rows = {r["question_id"]: r for r in prior["rows"] if r["variant"] == "rag4"}
    output = {"schema_version": "bounded-evidence-result-v1", "status": "succeeded", "annotation_status": pilot.annotation_status,
        "retrieval_report_sha256": args.report_sha256, "corpus_id": corpus.corpus_id, "extra_model_calls": 0,
        "config": {"max_context_chars": args.budget, "max_items": 10, "input_hits": 10,
            "selector_version": "evidence-floor-v2",
            "document_allocation": "same round-robin in both variants", "graph": False,
            "variable": "expand_parents"}, "variants": {}, "rows": [],
        "limitations": ["Frozen top-10 candidate replay, not a fresh online retrieval", "AI anchor labels are not human citation support",
            "Unanswerable questions retained, not refusal tested", "No graph quality gain or new embedding/chunking comparison claimed"]}
    source_files = [Path(__file__).resolve(), Path(__file__).resolve().parents[1] / "app/research/evidence.py"]
    output["executed_source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    for q in pilot.questions:
        hits = rows[q.id]["hits"]
        if any(corpus.chunks[h["id"]].text != h["text"] for h in hits):
            raise ValueError("Frozen hit identity or text mismatch")
        class Replay:
            def search(self, user_id, query, document_ids, top_k):
                return [VectorHit(chunk_id=h["id"], score=h["score"]) for h in hits[:top_k]]
        for variant, expand in (("child_only", False), ("bounded_parents", True)):
            bundle = HybridEvidenceEngine(corpus, Replay()).search(1, q.question, RetrievalOptions(
                document_ids=tuple(p.document_id for p in pilot.papers), max_context_chars=args.budget, expand_parents=expand, include_graph=False))
            candidates = [Candidate(i.chunk.chunk_id, i.chunk.document_id, i.chunk.chunk_index, i.chunk.text,
                tuple(Span(i.chunk.document_id, s.page_start, s.char_start, s.char_end) for s in i.chunk.source_locator.spans)) for i in bundle.items]
            metric = evidence_metrics(gold[q.id], candidates, ks=(10,))
            output["rows"].append({"question_id": q.id, "variant": variant, "bundle_id": bundle.bundle_id,
                "context_chars": bundle.context_chars, "warnings": bundle.warnings,
                "chunk_ids": [i.chunk.chunk_id for i in bundle.items], **metric})
    for variant in ("child_only", "bounded_parents"):
        scored = [r for r in output["rows"] if r["variant"] == variant and r["metrics"] is not None]
        output["variants"][variant] = {"scored": len(scored), "unanswerable_excluded": len(pilot.questions) - len(scored),
            "mean_anchor_coverage": sum(r["metrics"]["10"]["anchor_span_recall"] for r in scored) / len(scored),
            "complete_evidence_questions": sum(r["metrics"]["10"]["all_evidence_covered"] for r in scored),
            "mean_context_chars": sum(r["context_chars"] for r in scored) / len(scored)}
    (args.output / "report.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["variants"], ensure_ascii=True))


if __name__ == "__main__":
    main()
