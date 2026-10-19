"""Offline scope-only replay: fixed top-10, no refill, no model or SQL writes.

Scopes must be supplied independently of answer labels. Anchors are used only
after evidence selection to score this diagnostic, never in the selector.
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
from scripts.diagnose_evidence_gaps import covered


def replay_scope(corpus, hits, question, document_ids, budget=6000):
    corpus.require_scope(corpus.user_id, document_ids)
    options = RetrievalOptions(document_ids=document_ids, max_context_chars=budget, include_graph=False)
    candidates = []
    for h in hits[:10]:
        chunk = corpus.chunks.get(h['id'])
        if chunk is None or chunk.is_parent or chunk.text != h['text']:
            raise ValueError('Frozen candidate mismatch')
        hit = VectorHit(chunk_id=h['id'], score=h['score'])
        if chunk.document_id in document_ids:
            candidates.append(hit)
    class Replay:
        def search(self, *args):
            return candidates
    return HybridEvidenceEngine(corpus, Replay()).search(corpus.user_id, question, options)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pilot', 'sources', 'retrieval-report', 'scopes', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.retrieval_report.read_bytes()).hexdigest() != args.report_sha256:
        parser.error('Retrieval report digest mismatch')
    pilot = Pilot.model_validate_json(args.pilot.read_text(encoding='utf-8'))
    scope_input = json.loads(args.scopes.read_text(encoding='utf-8'))
    scopes = scope_input['document_scopes']
    questions = {q.id: q for q in pilot.questions}
    if not scopes or not set(scopes) <= set(questions):
        parser.error('Unknown or empty question scope')
    parsed = load_documents(pilot, args.sources)
    corpus = EvidenceCorpus(1, tuple(ChunkingEngine().split(adapt_parse_result(parsed[p.document_id],
        document_id=p.document_id, file_name=p.file_name), ChunkingConfig(child_max_tokens=600, parent_max_tokens=1800))
        for p in pilot.papers))
    prior = json.loads(args.retrieval_report.read_text(encoding='utf-8'))
    hits = {r['question_id']: r['hits'] for r in prior['rows'] if r['variant'] == 'rag4'}
    selected = []
    for qid, documents in scopes.items():
        for variant, scope in (('all_documents', tuple(corpus.chunk_sets)), ('explicit_scope', tuple(documents))):
            bundle = replay_scope(corpus, hits[qid], questions[qid].question, scope)
            selected.append((qid, variant, bundle))
    # Labels enter only after both variants have completed selection.
    gold = locate_evidence(pilot, parsed)
    rows = []
    for qid, variant, bundle in selected:
        spans = gold[qid]
        coverage = [any(covered(item.chunk, span) for item in bundle.items) for span in spans]
        rows.append({'question_id': qid, 'variant': variant, 'document_ids': bundle.options.document_ids,
            'covered_anchors': sum(coverage), 'total_anchors': len(spans), 'coverage': coverage,
            'context_chars': bundle.context_chars, 'bundle_id': bundle.bundle_id,
            'chunk_ids': [item.chunk.chunk_id for item in bundle.items], 'warnings': bundle.warnings})
    result = {'schema': 'evidence-scope-replay-v1', 'annotation_status': 'ai_draft', 'quality_gate_passed': False,
        'extra_model_calls': 0, 'max_context_chars': 6000, 'max_items': 10, 'retrieval_report_sha256': args.report_sha256,
        'scope_input': scope_input, 'scope_sha256': hashlib.sha256(args.scopes.read_bytes()).hexdigest(),
        'corpus_id': corpus.corpus_id, 'rows': rows,
        'limitations': ['Filtered frozen top-10 only, no refill or new query embeddings',
            'Maximum budgets equal; actual context lengths can differ',
            'AI anchor coverage is not semantic correctness or end-to-end quality'],
        'code_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).with_name('diagnose_evidence_gaps.py'),
            Path(__file__).resolve().parents[1] / 'app/research/evidence.py')}}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{k:r[k] for k in ('question_id','variant','covered_anchors','total_anchors','context_chars')} for r in rows]))


if __name__ == '__main__':
    main()
