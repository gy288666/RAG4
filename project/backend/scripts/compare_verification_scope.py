"""Frozen development comparisons, eight requests maximum, no automatic retry.

Context comparison: eight calls. Assertion controls/coverage: four calls each.
Human semantic acceptance is never inferred.
Creates a NEW SQL copy; original task, reports, sources and vectors stay intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

POLICIES = ('preceding-children-v1', 'cited-support-v2')
COMPOUND_STATEMENT = 'REALM利用检索到的文档来提高语言模型的预测能力，通过优化边缘似然性来训练检索器。'
PREDICTION_STATEMENT = 'REALM利用检索到的文档来提高语言模型的预测能力。'
TRAINING_STATEMENT = 'REALM通过优化边缘似然性来训练检索器。'


def frozen_cases(task, corpus, results):
    from scripts.reverify_research_claims import load_claim_file
    scope = tuple(s.document_id for s in task.sources)
    cases = [('realm_method_negative', load_claim_file(results / 'research_recovery_method_negative_20261108.json', corpus, scope), 'insufficient'),
             ('realm_method_positive', load_claim_file(results / 'research_recovery_method_positive_20261108.json', corpus, scope), 'supported')]
    for name, document, facet, expected in [('dpr_dataset_positive','dpr','dataset','supported'),
        ('fid_attribution_negative','fid','limitation','insufficient')]:
        claim = next(c for c in task.claims if c.document_id == document and c.facet == facet)
        claim.citation.validate_source(corpus, document)
        if claim.expected_id(corpus.corpus_id) != claim.claim_id: raise ValueError('Frozen claim identity changed')
        cases.append((name, claim, expected))
    return cases


def assertion_cases(task, corpus, results):
    """Manually frozen minimal pair; no general-purpose claim decomposition.

    Expected statuses are source-review drafts, not facts inferred by this code.
    New statements get new Claim identities and never inherit old verdicts.
    """
    from scripts.reverify_research_claims import load_claim_file
    scope = tuple(s.document_id for s in task.sources)
    negative, positive = (load_claim_file(results / f'research_recovery_method_{kind}_20261108.json',corpus,scope)
                          for kind in ('negative','positive'))
    if any(c.statement != COMPOUND_STATEMENT or c.facet != 'method' for c in (negative,positive)):
        raise ValueError('Frozen statement control changed')
    if negative.document_id != positive.document_id or negative.citation == positive.citation:
        raise ValueError('Frozen citation control changed')
    def derive(original, statement):
        claim = original.model_copy(update={'statement':statement})
        return claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
    return (('compound_original_quote',negative,'insufficient'),
            ('prediction_original_quote',derive(negative,PREDICTION_STATEMENT),'supported'),
            ('training_original_quote',derive(negative,TRAINING_STATEMENT),'insufficient'),
            ('training_covering_quote',derive(positive,TRAINING_STATEMENT),'supported'))


def experiment_cases(task, corpus, results, *, experiment='context-v1'):
    if experiment == 'context-v1': return frozen_cases(task,corpus,results), POLICIES
    if experiment == 'assertions-v1': return assertion_cases(task,corpus,results), (POLICIES[0],)
    if experiment == 'coverage-v1': return frozen_cases(task,corpus,results), (POLICIES[0],)
    raise ValueError('Unknown frozen comparison')


def coverage_expected(name):
    """Development source-review drafts, including atomic positive controls."""
    return {'realm_method_negative':('supported','insufficient'),
            'realm_method_positive':('supported','supported'),
            'dpr_dataset_positive':('supported',),
            'fid_attribution_negative':('insufficient',)}[name]


def coverage_plan(corpus,name,claim):
    from app.research.assertions import build_assertion_plan
    if name in {'realm_method_negative','realm_method_positive'}:
        if claim.statement!=COMPOUND_STATEMENT:raise ValueError('Frozen compound statement changed')
        ends=(claim.statement.index('，')+1,len(claim.statement))
    elif name in {'dpr_dataset_positive','fid_attribution_negative'}:
        ends=(len(claim.statement),)
    else:raise ValueError('Unknown coverage control')
    return build_assertion_plan(corpus,claim,ends)


def coverage_outcome(name,claim,review):
    expected=coverage_expected(name)
    if len(expected)!=len(review.plan.assertions):raise ValueError('Coverage control size mismatch')
    assessments={a.assertion_id:a for a in review.assessments}
    rows=[{'assertion_id':a.assertion_id,'char_start':a.char_start,'char_end':a.char_end,
           'expected_status':status,'actual_status':assessments[a.assertion_id].verdict(claim).status
               if a.assertion_id in assessments else 'missing'}
          for a,status in zip(review.plan.assertions,expected)]
    return {'verdict':review.verdict(claim).model_dump(mode='json'),
            'assertion_review':review.model_dump(mode='json'),'assertions':rows,
            'assertion_expectations_met':all(r['actual_status']==r['expected_status'] for r in rows)}


def select_coverage_case(cases,experiment,name):
    if name is None:return cases
    if experiment!='coverage-v1':raise ValueError('Single coverage control requires coverage-v1')
    selected=[case for case in cases if case[0]==name]
    if len(selected)!=1:raise ValueError('Unknown single coverage control')
    return selected


def comparison_spec(source,policy,response_format=None):
    from app.research.model import CompletionSpec
    return CompletionSpec.model_validate({**source.model_dump(),'verification_context_policy':policy,
        **({'response_format':response_format} if response_format is not None else {})})


def summary(rows, policies=POLICIES):
    result = {}
    for policy in policies:
        complete = [r for r in rows if r['policy'] == policy and 'verdict' in r]
        result[policy] = {'completed': len(complete), 'exact_status_matches': sum(r['verdict']['status'] == r['expected_status'] for r in complete),
            'false_accepts_against_agent_draft': sum(r['verdict']['status'] == 'supported' and r['expected_status'] != 'supported' for r in complete),
            'false_rejects_against_agent_draft': sum(r['verdict']['status'] != 'supported' and r['expected_status'] == 'supported' for r in complete)}
    return result


def diagnostic_exit_code(record):
    """0: all development expectations match; 2: incomplete; 3: mismatch.

    This gate concerns agent-draft diagnostics, never independent human quality.
    """
    rows = record.get('rows', [])
    limit = record.get('max_requests')
    if (record.get('status') != 'completed' or type(limit) is not int or limit <= 0
            or len(rows) != limit or any('verdict' not in row for row in rows)
            or len({(row.get('case'),row.get('policy')) for row in rows}) != limit):
        return 2
    return 0 if all(row['verdict']['status'] == row['expected_status']
                    and row.get('assertion_expectations_met',True) for row in rows) else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--task-name', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-live', required=True, action='store_true')
    parser.add_argument('--experiment', choices=('context-v1','assertions-v1','coverage-v1'), default='context-v1')
    parser.add_argument('--coverage-case',choices=('realm_method_negative','realm_method_positive','dpr_dataset_positive','fid_attribution_negative'))
    parser.add_argument('--response-format',choices=('text','json_object'),default=None,
                        help='Explicit format comparison; no silent repair or fallback')
    parser.add_argument('--fail-on-draft-mismatch', action='store_true',
                        help='Exit 3 if completed judgments differ from agent draft; not a human quality gate')
    args = parser.parse_args()
    if args.coverage_case is not None and args.experiment!='coverage-v1':parser.error('--coverage-case requires coverage-v1')
    source, output = args.source_run.resolve(), args.output.resolve()
    if output == source or source in output.parents or output in source.parents: raise ValueError('Output aliases retained input')
    if Path(args.task_name).name != args.task_name: raise ValueError('Task name must be a simple file name')
    output.mkdir(parents=True, exist_ok=False)
    database = source / 'snapshot.sqlite'
    task_path = source / args.task_name
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    old_task_sha, old_db_sha = sha(task_path), sha(database)
    vector_sha = {p.name: sha(p) for p in (source / 'vectors').glob('*.json')}
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as old, sqlite3.connect(output / 'snapshot.sqlite') as copied:
        old.backup(copied)
    os.environ['ENV_FILE'] = str(output / 'absent.env')
    os.environ['DATABASE_URL'] = 'sqlite:///' + (output / 'snapshot.sqlite').as_posix()
    from app.research.tasks import ResearchTask
    from app.research.model import CompletionSpec, JsonResearchModel
    from app.research.artifacts import EvidenceVerifier
    from app.services.vector_store import LocalVectorStore
    from scripts.reverify_research_claims import frozen_corpus
    from scripts.research_acceptance_guard import AcceptanceTransport
    import httpx
    task = ResearchTask.model_validate_json(task_path.read_bytes())
    vectors = LocalVectorStore(str(source / 'vectors'))
    corpus = frozen_corpus(task, vectors)
    cases, policies = experiment_cases(task, corpus, Path(__file__).resolve().parents[1] / 'evaluation/results',experiment=args.experiment)
    cases=select_coverage_case(cases,args.experiment,args.coverage_case)
    plans={name:coverage_plan(corpus,name,claim) for name,claim,_ in cases} if args.experiment=='coverage-v1' else {}
    request_limit = len(cases)*len(policies)
    if task.completion.endpoint != 'https://api.siliconflow.cn/v1/chat/completions': raise ValueError('Credential binding mismatch')
    key = os.environ.get('RAG4_EVAL_API_KEY')
    if not key:
        keys = set(re.findall(r'sk-[A-Za-z0-9_-]{20,}', Path('E:/RAG3/提示.txt').read_text(encoding='utf-8-sig')))
        if len(keys) != 1: raise ValueError('Provide one key in process environment')
        key = keys.pop()
    guard = AcceptanceTransport(completion_limit=request_limit, embedding_limit=1)
    rows = []
    record = {'date':'2026-11-08', 'annotation_status':'primary_agent_source_review_draft', 'quality_gate_passed':False,
        'source_task_sha256':old_task_sha, 'model_id':task.completion.model_id, 'max_requests':request_limit, 'automatic_retries':0,
        'experiment':args.experiment, 'policies':policies, 'rows':rows, 'money_cost':'unknown',
        'response_format_override':args.response_format,
        'frozen_claims':[{'case':name,'expected_status':expected,'claim':claim.model_dump(mode='json')} for name,claim,expected in cases]}
    if plans:
        record['frozen_plans']={name:plan.model_dump(mode='json') for name,plan in plans.items()}
        record['expected_assertions']={name:coverage_expected(name) for name in plans}
    # Retain the exact planned input even if the first provider call is interrupted.
    record['status']='running'
    (output/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    class MeasuredModel(JsonResearchModel):
        def generate(self, operation, payload):
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            self.measure = {'payload_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'payload_chars':len(raw),
                'context_chars':sum(len(c['context']) for c in payload['claims']),
                'source_chars':sum(len(s['text']) for c in payload['claims'] for s in c['sources'])}
            return super().generate(operation, payload)
    try:
        with httpx.Client(transport=guard, timeout=httpx.Timeout(60, connect=5)) as client:
            for name, claim, expected in cases:
                for policy in policies:
                    frozen_corpus(task, vectors)
                    spec = comparison_spec(task.completion,policy,args.response_format)
                    model = MeasuredModel(spec, api_key=key, max_calls=1, client=client)
                    row = {'case':name,'claim_id':claim.claim_id,'expected_status':expected,'policy':policy}
                    rows.append(row)
                    try:
                        if plans:
                            from app.research.assertions import AssertionCoverageVerifier
                            review,=AssertionCoverageVerifier(model).verify(corpus,(claim,),(plans[name],))
                            row.update(coverage_outcome(name,claim,review))
                        else:
                            report = EvidenceVerifier(model).verify(corpus, (claim,))
                            row.update(verdict=report.verdicts[0].model_dump(mode='json'), verification=report.model_dump(mode='json'))
                        frozen_corpus(task, vectors)
                    except Exception as error:
                        row.update(error_type=type(error).__name__, diagnostics=getattr(error,'diagnostics',()))
                        raise
                    finally:
                        row.update(input=getattr(model,'measure',{}), calls=model.calls)
                        (output/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps({'case':name,'policy':policy,'status':row['verdict']['status']}),flush=True)
            record['status'] = 'completed'
    except Exception as error:
        record.update(status='stopped', error_type=type(error).__name__)
    finally:
        record.update(development_expectations_met=diagnostic_exit_code(record)==0,
            summary=summary(rows,policies), requests=guard.calls, original_task_unchanged=sha(task_path)==old_task_sha,
            original_database_unchanged=sha(database)==old_db_sha,
            original_vectors_unchanged={p.name:sha(p) for p in (source/'vectors').glob('*.json')}==vector_sha)
        (output/'report.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return diagnostic_exit_code(record) if args.fail_on_draft_mismatch else (0 if record['status']=='completed' else 2)


if __name__ == '__main__': raise SystemExit(main())
