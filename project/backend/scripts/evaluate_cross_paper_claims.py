"""Six frozen DPR/FiD diagnostic claims, one v5 call each, no hidden retries.

These are development transfer cases, not a blind or human-labelled holdout.
Statements change; exact citations, corpus, prompts and model settings do not.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def diagnostic_status(runs):
    """Separate transport success, development assertions and human quality."""
    if not runs or any(r['replay']['status']!='succeeded' for r in runs):
        return 'execution_failed',1
    if any(not r.get('verdict_matches') or not r.get('checks_match') for r in runs):
        return 'expectation_mismatch',2
    return 'development_expectations_met',0


def build_cases(task):
    from app.research.artifacts import Claim
    originals={(c['document_id'],c['facet']):Claim.model_validate(c) for c in task['claims']}
    definitions=(
        ('dpr_qualified_result','dpr','dataset','result',
            '在Natural Questions开发集上，使用1,000个训练样本的DPR已经优于BM25。',
            'supported',{'conditions':'supported'}),
        ('dpr_omitted_conditions','dpr','dataset','result',
            'DPR在所有数据集上均优于BM25，不受训练样本数量和评估集影响。',
            'not_supported',{'conditions':'not_supported'}),
        ('dpr_explicit_limitation','dpr','limitation','limitation',
            '在缺少给定段落时，SQuAD的许多问题缺少上下文，因此它并非理想的开放域问答数据集。',
            'supported',{'conditions':'supported','entailment':'supported'}),
        ('dpr_mixed_scope','dpr','limitation','limitation',
            '在缺少给定段落时，SQuAD的许多问题缺少上下文，因此DPR无法处理任何开放域问答数据集。',
            'not_supported',{'entailment':'not_supported'}),
        ('fid_own_method','fid','method','method',
            'Fusion-in-Decoder在编码器中独立处理各段落，在解码器中联合处理段落表示。',
            'supported',{'attribution':'supported','conditions':'supported'}),
        ('fid_wrong_attribution','fid','limitation','limitation',
            'Fusion-in-Decoder本身必须把所有信息存入模型权重，因而需要数十亿参数且查询和训练成本昂贵。',
            'not_supported',{'attribution':'not_supported'}),
    )
    cases=[]
    for name,document,source_facet,facet,statement,expected,checks in definitions:
        original=originals[document,source_facet]
        claim=original.model_copy(update={'facet':facet,'statement':statement})
        claim=claim.model_copy(update={'claim_id':claim.expected_id(task['corpus_id'])})
        cases.append({'case_id':name,'source_claim_id':original.claim_id,
            'claim':claim.model_dump(mode='json'),'expected':expected,'required_checks':checks})
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score-report',type=Path,help='Offline assertion check, no model calls or report writes')
    for name in ('task','database','vectors','output'):
        parser.add_argument('--'+name,type=Path)
    control_input=parser.add_mutually_exclusive_group()
    control_input.add_argument('--control-tests',type=Path)
    control_input.add_argument('--control-report',type=Path,help='Freeze current implementation from a complete context comparison')
    parser.add_argument('--verification-context-policy',choices=('cited-chunk-v1','preceding-children-v1'),default='cited-chunk-v1')
    args=parser.parse_args()
    if args.score_report:
        status,code=diagnostic_status(json.loads(args.score_report.read_text(encoding='utf-8'))['runs'])
        print(json.dumps({'diagnostic_status':status,'quality_gate_passed':False,'extra_model_calls':0}))
        return code
    if not all((args.task,args.database,args.vectors,args.output)) or not (args.control_tests or args.control_report):
        parser.error('Live evaluation requires task/database/vectors/output and one frozen control')
    backend=Path(__file__).resolve().parents[1]
    control_raw=(args.control_tests or args.control_report).read_bytes()
    control=json.loads(control_raw)
    if args.control_report:
        expected_names={p.name for p in (backend/'app/research').glob('*.py')}
        if set(control['code_sha256'])-{'evaluate_context_attribution.py'}!=expected_names:
            raise ValueError('Frozen context implementation inventory differs')
    fingerprints=control['unchanged_production_sha256'] if args.control_tests else {
        'app/research/'+name:h for name,h in control['code_sha256'].items() if name!='evaluate_context_attribution.py'}
    for filename,digest in fingerprints.items():
        if hashlib.sha256((backend/filename).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen verification implementation changed')
    raw=args.task.read_bytes();source=json.loads(raw)
    if args.control_report:
        if hashlib.sha256(raw).hexdigest()!=control['source_task_sha256']:
            raise ValueError('Frozen context control source lineage mismatch')
        if hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest()!=control['replay_script_sha256']:
            raise ValueError('Frozen context replay implementation changed')
    cases=build_cases(source)
    if len(cases)!=6 or len({c['claim']['claim_id'] for c in cases})!=6:
        raise ValueError('Diagnostic cases must have unique identities')
    args.output.mkdir(parents=True,exist_ok=False)
    fixture=json.dumps(cases,ensure_ascii=False,indent=2).encode('utf-8')
    (args.output/'cases.json').write_bytes(fixture)
    report={'schema':'cross-paper-claim-diagnostic-v1','max_requests':6,'protocol':'facet-handles-v5',
        'quality_gate_passed':False,'annotation_status':'development_ai_expectations',
        'source_task_sha256':hashlib.sha256(raw).hexdigest(),
        ('control_tests_sha256' if args.control_tests else 'control_report_sha256'):hashlib.sha256(control_raw).hexdigest(),
        'fixture_sha256':hashlib.sha256(fixture).hexdigest(),'cases':cases,'calls':[],'runs':[],
        'max_output_tokens':4096,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'replay_script_sha256':hashlib.sha256((backend/'scripts/reverify_research_claims.py').read_bytes()).hexdigest(),
        'frozen_production_sha256':fingerprints,'verification_context_policy':args.verification_context_policy,
        'limitations':['Six AI-authored cases from two already available papers; not a blind holdout or human validation',
            'One call per case, no v4 comparison in this experiment; do not infer general improvement',
            'No new extraction or end-to-end comparison; default production policy is unchanged']}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for case in cases:
        claim_file=args.output/(case['case_id']+'.json')
        claim_file.write_bytes(json.dumps(case['claim'],ensure_ascii=False,indent=2).encode('utf-8'))
        child=args.output/(case['case_id']+'-run')
        result=subprocess.run([sys.executable,str(backend/'scripts/reverify_research_claims.py'),
            '--task',str(args.task),'--database',str(args.database),'--vectors',str(args.vectors),
            '--claim-file',str(claim_file),'--protocol','facet-handles-v5','--max-output-tokens','4096',
            '--verification-context-policy',args.verification_context_policy,
            '--output',str(child)],check=False)
        child_raw=(child/'report.json').read_bytes();run=json.loads(child_raw)
        row={'case_id':case['case_id'],'exit_code':result.returncode,
            'report_sha256':hashlib.sha256(child_raw).hexdigest(),'replay':run}
        if run['status']=='succeeded':
            verdict=run['verification']['verdicts'][0]
            assessment=run['verification']['assessments'][0]
            matches=lambda value,expected:value=='supported' if expected=='supported' else value!='supported'
            row.update(expected=case['expected'],actual=verdict['status'],
                verdict_matches=matches(verdict['status'],case['expected']),
                checks={n:assessment[n]['status'] for n in ('attribution','conditions','entailment')},
                checks_match=all(matches(assessment[n]['status'],expected) for n,expected in case['required_checks'].items()))
        report['runs'].append(row)
        report['calls'].extend({**c,'case_id':case['case_id']} for c in run['calls'])
        save()
        if len(report['calls'])>6:raise RuntimeError('Request cap exceeded')
        print(json.dumps({'case_id':case['case_id'],'status':run['status'],
            'actual':row.get('actual'),'verdict_matches':row.get('verdict_matches'),
            'checks_match':row.get('checks_match')}),flush=True)
    report['diagnostic_status'],code=diagnostic_status(report['runs'])
    save()
    return code


if __name__=='__main__':
    raise SystemExit(main())
