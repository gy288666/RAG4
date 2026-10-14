"""Offline anchor-gap diagnosis, never used to select production evidence.

Uses AI draft anchors for development diagnosis only; no model calls or SQL.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.chunking import ChunkingConfig, ChunkingEngine
from app.chunking.adapter import adapt_parse_result
from app.evaluation.literature import Pilot, load_documents, locate_evidence
from app.research.evidence import EvidenceCorpus, HybridEvidenceEngine, RetrievalOptions, VectorHit


def covered(chunk, span):
    if chunk.document_id != span.document_id:
        return False
    position = span.start
    for source in sorted(chunk.source_locator.spans, key=lambda s: s.char_start):
        if source.page_start == span.page and source.char_start <= position:
            position = max(position, source.char_end)
    return position >= span.end


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--retrieval-report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.retrieval_report.read_bytes()).hexdigest() != args.report_sha256:
        parser.error("Retrieval report digest mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    pilot = Pilot.model_validate_json(args.pilot.read_text(encoding="utf-8"))
    parsed = load_documents(pilot, args.sources)
    corpus = EvidenceCorpus(1, tuple(ChunkingEngine().split(adapt_parse_result(parsed[p.document_id],
        document_id=p.document_id, file_name=p.file_name), ChunkingConfig(child_max_tokens=600, parent_max_tokens=1800))
        for p in pilot.papers))
    gold = locate_evidence(pilot, parsed)
    report = json.loads(args.retrieval_report.read_text(encoding="utf-8"))
    rows = []
    for question in pilot.questions:
        if question.id not in {"q09", "q12"}:
            continue
        hits = next(r["hits"] for r in report["rows"] if r["variant"] == "rag4" and r["question_id"] == question.id)[:10]
        if any(corpus.chunks[h["id"]].text != h["text"] for h in hits):
            raise ValueError("Frozen candidate mismatch")

        class Replay:
            def search(self, *args):
                return [VectorHit(chunk_id=h["id"], score=h["score"]) for h in hits]

        bundle = HybridEvidenceEngine(corpus, Replay()).search(1, question.question, RetrievalOptions(
            document_ids=tuple(p.document_id for p in pilot.papers), max_context_chars=6000, include_graph=False))
        parent_ids = tuple(dict.fromkeys(corpus.chunks[h["id"]].parent_chunk_id for h in hits))
        for span in gold[question.id]:
            is_covered = any(covered(i.chunk, span) for i in bundle.items)
            parents = []
            for identity in parent_ids:
                parent = corpus.chunks[identity]
                if not covered(parent, span):
                    continue
                members = [i for i in bundle.items if i.chunk.parent_chunk_id == identity or i.chunk.chunk_id == identity]
                parents.append({"chunk_id": identity, "chars": len(parent.text),
                    "additional_chars": len(parent.text)-sum(len(i.chunk.text) for i in members)})
            remaining = 6000-bundle.context_chars
            reason = "covered" if is_covered else "anchor_retrieval_gap" if not parents else (
                "parent_context_budget" if min(p["additional_chars"] for p in parents) > remaining else "selection_policy_gap")
            rows.append({"question_id": question.id, "document_id": span.document_id, "page": span.page,
                "anchor_char_start": span.start, "anchor_char_end": span.end, "covered": is_covered,
                "reason": reason, "context_chars": bundle.context_chars, "remaining_chars": remaining,
                "candidate_parents": parents, "bundle_id": bundle.bundle_id})
    output = {"schema":"evidence-gap-diagnosis-v1", "status":"succeeded", "annotation_status":"ai_draft",
        "extra_model_calls":0, "retrieval_report_sha256":args.report_sha256, "corpus_id":corpus.corpus_id,
        "rows":rows, "limitations":["Anchor diagnosis, not semantic equivalence or answer quality",
            "Gold anchors used only for offline diagnosis, never in retrieval prompts", "Same 6000-character budget and evidence-floor-v2"],
        "executed_source_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).resolve().parents[1]/"app/research/evidence.py")}}
    (args.output/"report.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"rows":len(rows),"gaps":[r["reason"] for r in rows if not r["covered"]]}))


if __name__ == "__main__":
    main()
