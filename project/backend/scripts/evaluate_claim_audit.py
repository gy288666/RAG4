"""Bounded paired diagnosis of four unchanged R33 claims; never a quality gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def cases_for(task):
    """Development expectations from R33 source inspection, not human labels."""
    definitions = (
        ('realm', 'method', 'not_supported', {'entailment': 'not_supported'}),
        ('realm', 'result', 'not_supported', {'conditions': 'not_supported'}),
        ('dpr', 'dataset', 'supported', {'entailment': 'supported'}),
        ('fid', 'result', 'supported', {'entailment': 'supported'}),
    )
    cases = []
    for document, facet, expected, checks in definitions:
        claims = [c for c in task['claims'] if (c['document_id'], c['facet']) == (document, facet)]
        if len(claims) != 1:
            raise ValueError('Diagnostic requires exactly one original claim per selected facet')
        cases.append(dict(case_id=document+'_'+facet, claim=claims[0], expected=expected, required_checks=checks))
    return cases


def score(cases, verification):
    from app.research.artifacts import VerificationReport, Claim
    from scripts.evaluate_verification_facets import outcome
    report = VerificationReport.model_validate(verification)
    rows = [outcome({**c, 'claim': Claim.model_validate(c['claim'])}, report) for c in cases]
    by_claim = {a.claim_id: a for a in report.assessments}
    for row in rows:
        assessment = by_claim[row['claim_id']]
        row['invalid_support_checks'] = [name for name in ('attribution', 'conditions', 'entailment')
                                        if getattr(assessment, name).reason.startswith('unknown_support_id_or_invalid_span:')]
        row['semantic_match'] = bool(row['verdict_matches'] and row['checks_match'] and not row['invalid_support_checks'])
    return {'rows': rows, 'matched': sum(r['verdict_matches'] and r['checks_match'] for r in rows),
            'semantic_matched': sum(r['semantic_match'] for r in rows),
            'total': len(rows), 'quality_gate_passed': False}


def model_treatment(model_id, catalog, control, source, cases, backend):
    """Admit one model-only treatment against complete, unchanged R34 controls."""
    if model_id not in catalog['candidates'] or model_id == source['completion']['model_id']:
        raise ValueError('Treatment must be a different provider-listed model')
    if control['cases'] != cases:
        raise ValueError('Control claims differ')
    inventory = {str(p.relative_to(backend)).replace('\\', '/') for p in (backend/'app/research').glob('*.py')}
    if inventory != {p for p in control['code_sha256'] if p.startswith('app/research/')}:
        raise ValueError('Control implementation inventory differs')
    for name in inventory:
        if hashlib.sha256((backend/name).read_bytes()).hexdigest() != control['code_sha256'][name]:
            raise ValueError('Control research implementation changed')
    baseline = [r for r in control['runs'] if r['version'] == 'research-operator-v1']
    if len(baseline) != 4 or {r['case_id'] for r in baseline} != {c['case_id'] for c in cases}:
        raise ValueError('Four complete old-prompt controls required')
    from app.research.model import CompletionSpec, prompt_for
    spec = CompletionSpec.model_validate({**source['completion'], 'version': 'research-operator-v1'})
    prompt_sha = hashlib.sha256(prompt_for(spec, 'verify_facets').encode()).hexdigest()
    scores = []
    for case in cases:
        row = next(r for r in baseline if r['case_id'] == case['case_id'])
        calls = [c for c in control['calls'] if c['case_id'] == case['case_id'] and c['version'] == 'research-operator-v1']
        if (row['status'] != 'succeeded' or len(calls) != 1 or calls[0]['status'] != 'succeeded'
                or calls[0]['model_id'] != spec.model_id or calls[0]['prompt_sha256'] != prompt_sha):
            raise ValueError('Control model call or prompt differs')
        scores.append(dict(case_id=case['case_id'], score=score([case], row['verification'])))
    return scores


def treatment_spec(source, version, model_id=None):
    from app.research.model import CompletionSpec
    overrides = {'version': version}
    if model_id is not None:
        overrides['model_id'] = model_id
    return CompletionSpec.model_validate({**source.model_dump(), **overrides})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-record', type=Path, required=True)
    parser.add_argument('--score-original', action='store_true', help='Offline; no credentials, SQL or model')
    parser.add_argument('--model-id', help='Model-only treatment: four calls with the unchanged old prompt')
    parser.add_argument('--control-report', type=Path, help='Public R34 paired experiment record')
    parser.add_argument('--model-catalog', type=Path, help='Provider model listing recorded before this experiment')
    for name in ('task', 'database', 'vectors', 'output'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    original = json.loads(args.source_record.read_text(encoding='utf-8'))
    cases = cases_for(original)
    if args.score_original:
        result = score(cases, original['artifact']['verification'])
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result['semantic_matched'] == result['total'] else 2
    if not all((args.task, args.database, args.vectors, args.output)):
        parser.error('Live diagnosis requires task/database/vectors/output')
    raw = args.task.read_bytes()
    if hashlib.sha256(raw).hexdigest() != original['checkpoint_sha256']['final_task']:
        raise ValueError('Source task differs from frozen R33 record')
    source = json.loads(raw)
    if cases != cases_for(source):
        raise ValueError('Original diagnostic claims changed')
    if source['completion']['endpoint'] != 'https://api.siliconflow.cn/v1/chat/completions':
        raise ValueError('Unexpected credential binding')
    backend = Path(__file__).resolve().parents[1]
    if bool(args.model_id) != bool(args.control_report and args.model_catalog):
        parser.error('Model treatment requires model-id/control-report/model-catalog together')
    if not args.model_id and (args.control_report or args.model_catalog):
        parser.error('Control and catalog require model-id')
    control_scores = None
    if args.model_id:
        control_raw = args.control_report.read_bytes()
        catalog_raw = args.model_catalog.read_bytes()
        control = json.loads(control_raw)['live_report']
        if control['source_task_sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('Control source task differs')
        control_scores = model_treatment(args.model_id, json.loads(catalog_raw), control, source, cases, backend)
    key = os.environ['RAG4_EVAL_API_KEY']
    args.output.mkdir(parents=True, exist_ok=False)
    target = args.output.resolve()/'snapshot.sqlite'
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as old, sqlite3.connect(target) as new:
        old.backup(new)
    os.environ['ENV_FILE'] = str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL'] = 'sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI'] = 'false'
    from app.research.tasks import ResearchTask
    from app.research.artifacts import Claim, EvidenceVerifier
    from app.research.model import JsonResearchModel
    from app.research.store import SQLResearchTaskStore
    from app.services.vector_store import LocalVectorStore
    from scripts.reverify_research_claims import frozen_corpus
    task = ResearchTask.model_validate_json(raw)
    if SQLResearchTaskStore().load(task.user_id, task.id) != task:
        raise ValueError('SQL and JSON checkpoints differ')
    vectors = LocalVectorStore(str(args.vectors))
    digest_vectors = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.vectors.glob('*.json')}
    before = digest_vectors()
    corpus = frozen_corpus(task, vectors)
    for case in cases:
        claim = Claim.model_validate(case['claim'])
        claim.citation.validate_source(corpus, claim.document_id)
        if claim.claim_id != claim.expected_id(corpus.corpus_id):
            raise ValueError('Claim identity differs')
    versions = ('research-operator-v1',) if args.model_id else ('research-operator-v1', 'research-facet-audit-v2')
    report = dict(schema='paired-claim-audit-v1', date='2026-11-01', quality_gate_passed=False,
                  annotation_status='development_ai_expectations', max_requests=len(cases)*len(versions), cases=cases, runs=[], calls=[],
                  original_source_sha256=hashlib.sha256(args.source_record.read_bytes()).hexdigest(),
                  source_task_sha256=hashlib.sha256(raw).hexdigest(), vector_sha256=before,
                  code_sha256={str(p.relative_to(backend)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [Path(__file__)]+list((backend/'app/research').glob('*.py'))},
                  limitations=['Four previously inspected development cases, not a blind or human holdout',
                               'Single vs historical batch is a separate comparison; paired prompt test fixes single-claim composition',
                               'No new extraction, production activation or automatic retry'])
    if args.model_id:
        report.update(schema='model-only-claim-audit-v1', treatment_model=args.model_id,
                      treatment_completion=treatment_spec(task.completion, 'research-operator-v1', args.model_id).model_dump(mode='json'),
                      control_report_sha256=hashlib.sha256(control_raw).hexdigest(),
                      model_catalog_sha256=hashlib.sha256(catalog_raw).hexdigest(), control_scores=control_scores)
        report['limitations'] = ['Four previously inspected development cases, not a blind or human holdout',
                                'Historical single-claim control, not a simultaneous randomized trial; provider drift remains possible',
                                'Only model ID changes; no extraction, activation or automatic retry']
    def save():
        (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    for case in cases:
        for version in versions:
            if len(report['calls']) >= report['max_requests']:
                raise RuntimeError('Request cap exhausted')
            spec = treatment_spec(task.completion, version, args.model_id)
            model = JsonResearchModel(spec, api_key=key, max_calls=1)
            row = dict(case_id=case['case_id'], version=version, model_id=spec.model_id)
            try:
                corpus = frozen_corpus(task, vectors)
                verification = EvidenceVerifier(model).verify(corpus, (Claim.model_validate(case['claim']),))
                frozen_corpus(task, vectors)
                row.update(status='succeeded', verification=verification.model_dump(mode='json'),
                           score=score([case], verification.model_dump(mode='json')))
            except Exception as error:
                row.update(status='failed', error_type=type(error).__name__)
            report['calls'].extend(dict(c, case_id=case['case_id']) for c in model.calls)
            report['runs'].append(row)
            save()
            print(json.dumps({k: row.get(k) for k in ('case_id', 'version', 'status', 'score')}, ensure_ascii=True), flush=True)
    if before != digest_vectors():
        raise ValueError('Source vectors changed')
    report['source_vectors_unchanged'] = True
    save()
    if any(r['status'] != 'succeeded' for r in report['runs']):
        return 1
    judged = report['runs'] if args.model_id else [r for r in report['runs'] if r['version']=='research-facet-audit-v2']
    return 0 if all(r['score']['semantic_matched'] == 1 for r in judged) else 2


if __name__ == '__main__':
    raise SystemExit(main())
