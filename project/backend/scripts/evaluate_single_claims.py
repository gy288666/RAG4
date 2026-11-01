"""Four single-claim calls against the frozen batched verification comparison.

Hypothesis test only: v4/v5 x method/limitation, no hidden retries. Credentials
are inherited in the environment and never copied into the manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('task','database','vectors','batched-report','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    task_raw=args.task.read_bytes()
    source=json.loads(task_raw)
    batch_raw=args.batched_report.read_bytes()
    batch=json.loads(batch_raw)
    if hashlib.sha256(task_raw).hexdigest()!=batch['source_task_sha256']:
        raise ValueError('Batched comparison lineage mismatch')
    backend=Path(__file__).resolve().parents[1]
    # Freeze the prompt/policy implementation used by the batched control.
    for filename,digest in batch['code_sha256'].items():
        if filename=='evaluate_verification_facets.py':continue
        if hashlib.sha256((backend/'app/research'/filename).read_bytes()).hexdigest()!=digest:
            raise ValueError('Batched comparison source code changed')
    cases=[]
    for case_id in ('real_method','real_invented_future_work'):
        case=next(c for group in batch['fixture'] if group['group']=='real' for c in group['cases'] if c['case_id']==case_id)
        claim=next(c for c in source['claims'] if c['claim_id']==case['claim']['claim_id'])
        if claim!=case['claim']:raise ValueError('Frozen claim differs')
        cases.append(case)
    args.output.mkdir(parents=True,exist_ok=False)
    report={'schema':'single-claim-comparison-v1','max_requests':4,'calls':[],'runs':[],
        'quality_gate_passed':False,'annotation_status':'development_ai_expectations',
        'source_task_sha256':hashlib.sha256(task_raw).hexdigest(),
        'batched_report_sha256':hashlib.sha256(batch_raw).hexdigest(),
        'max_output_tokens':4096,'fixed_case_ids':[c['case_id'] for c in cases],
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'replay_script_sha256':hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest(),
        'limitations':['Two cases and one call per cell; no repeated statistical test or human adjudication',
            'Single vs batched changes request composition and token count; model randomness remains',
            'Previous real v5 batch timed out and cannot be scored as a semantic failure']}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for case in cases:
        for protocol in ('source-handles-v4','facet-handles-v5'):
            child=args.output/(case['case_id']+'-'+protocol)
            command=[sys.executable,str(backend/'scripts/reverify_research_claims.py'),
                '--task',str(args.task),'--database',str(args.database),'--vectors',str(args.vectors),
                '--output',str(child),'--protocol',protocol,'--max-output-tokens','4096',
                '--claim-id',case['claim']['claim_id']]
            result=subprocess.run(command,check=False)
            raw=(child/'report.json').read_bytes()
            run=json.loads(raw)
            row={'case_id':case['case_id'],'protocol':protocol,'exit_code':result.returncode,
                'report_sha256':hashlib.sha256(raw).hexdigest(),'replay':run}
            if run['status']=='succeeded':
                verification=run['verification'];verdict=verification['verdicts'][0]
                assessment=verification['assessments'][0]
                matches=lambda value,expect: value=='supported' if expect=='supported' else value!='supported'
                row.update(actual=verdict['status'],expected=case['expected'],
                    verdict_matches=matches(verdict['status'],case['expected']),
                    checks={n:assessment[n]['status'] for n in ('attribution','conditions','entailment')},
                    required_checks=case['required_checks'],
                    checks_match=all(matches(assessment[n]['status'],expected) for n,expected in case['required_checks'].items()))
            report['runs'].append(row)
            report['calls'].extend({**c,'case_id':case['case_id']} for c in run['calls'])
            save()
            if len(report['calls'])>4:raise RuntimeError('Request cap exceeded')
            print(json.dumps({'case_id':case['case_id'],'protocol':protocol,'status':run['status'],
                'actual':row.get('actual'),'checks_match':row.get('checks_match')}),flush=True)
    return 0 if all(r['replay']['status']=='succeeded' for r in report['runs']) else 1


if __name__=='__main__':
    raise SystemExit(main())
