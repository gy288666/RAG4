"""Four calls, two FiD cases x old/new context. Prompts and citations fixed."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('task','database','vectors','control-report','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    backend=Path(__file__).resolve().parents[1]
    source=args.task.read_bytes();control_raw=args.control_report.read_bytes();control=json.loads(control_raw)
    if hashlib.sha256(source).hexdigest()!=control['source_task_sha256']:
        raise ValueError('Context experiment source lineage mismatch')
    task=json.loads(source)
    cases=[next(c for c in control['cases'] if c['case_id']==name)
        for name in ('fid_wrong_attribution','fid_own_method')]
    originals={c['claim_id']:c for c in task['claims']}
    for case in cases:
        if case['claim']['citation']!=originals[case['source_claim_id']]['citation']:
            raise ValueError('Context experiment citation changed')
    args.output.mkdir(parents=True,exist_ok=False)
    fixture=json.dumps(cases,ensure_ascii=False,indent=2).encode('utf-8')
    (args.output/'cases.json').write_bytes(fixture)
    report={'schema':'verification-context-comparison-v1','max_requests':4,'calls':[],'runs':[],
        'protocol':'facet-handles-v5','max_output_tokens':4096,'quality_gate_passed':False,
        'annotation_status':'development_ai_expectations','source_task_sha256':hashlib.sha256(source).hexdigest(),
        'control_report_sha256':hashlib.sha256(control_raw).hexdigest(),'fixture_sha256':hashlib.sha256(fixture).hexdigest(),
        'cases':cases,'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__)]+list((backend/'app/research').glob('*.py'))},
        'replay_script_sha256':hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest(),
        'limitations':['Two already inspected FiD cases; no blind holdout, repeated trials or human adjudication',
            'Context policy changes source composition and token count; default remains unchanged']}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for case in cases:
        path=args.output/(case['case_id']+'.json')
        path.write_bytes(json.dumps(case['claim'],ensure_ascii=False,indent=2).encode('utf-8'))
        for policy in ('cited-chunk-v1','preceding-children-v1'):
            child=args.output/(case['case_id']+'-'+policy)
            result=subprocess.run([sys.executable,str(backend/'scripts/reverify_research_claims.py'),
                '--task',str(args.task),'--database',str(args.database),'--vectors',str(args.vectors),
                '--claim-file',str(path),'--protocol','facet-handles-v5','--verification-context-policy',policy,
                '--max-output-tokens','4096','--output',str(child)],check=False)
            raw=(child/'report.json').read_bytes();run=json.loads(raw)
            row={'case_id':case['case_id'],'context_policy':policy,'exit_code':result.returncode,
                'report_sha256':hashlib.sha256(raw).hexdigest(),'replay':run}
            if run['status']=='succeeded':
                report_v=run['verification'];verdict=report_v['verdicts'][0];check=report_v['assessments'][0]
                matches=lambda actual,expected:actual=='supported' if expected=='supported' else actual!='supported'
                row.update(actual=verdict['status'],expected=case['expected'],
                    verdict_matches=matches(verdict['status'],case['expected']),
                    checks={n:check[n]['status'] for n in ('attribution','conditions','entailment')},
                    checks_match=all(matches(check[n]['status'],expected) for n,expected in case['required_checks'].items()))
            report['runs'].append(row);report['calls'].extend({**c,'case_id':case['case_id']} for c in run['calls']);save()
            if len(report['calls'])>4:raise RuntimeError('Context experiment cap exceeded')
            print(json.dumps({'case_id':case['case_id'],'policy':policy,'status':run['status'],
                'actual':row.get('actual'),'checks_match':row.get('checks_match')}),flush=True)
    treatment=[r for r in report['runs'] if r['context_policy']=='preceding-children-v1']
    report['treatment_expectations_met']=len(treatment)==2 and all(
        r.get('verdict_matches') and r.get('checks_match') for r in treatment)
    save()
    if not all(r['replay']['status']=='succeeded' for r in report['runs']):return 1
    return 0 if report['treatment_expectations_met'] else 2


if __name__=='__main__':
    raise SystemExit(main())
