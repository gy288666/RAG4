"""Replay frozen claims through durable document batches, with an explicit cap.

Fresh replay uses a new task ID; continuation copies its retained SQL state.
Source task, parent checkpoint and active version are untouched.
The saved search/analysis steps are reused, not billed as newly executed steps.
Resume is explicit and keeps both the checkpoint and the original request cap.
--continue-from requires a separate output and an explicit finite new budget.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fork_checkpoint(parent, output, source_sha, new_budget):
    """Start a separate bounded experiment from retained SQL state."""
    if type(new_budget) is not int or not 1 <= new_budget <= 6:
        raise ValueError('A finite new request budget is required')
    raw = (parent/'report.json').read_bytes()
    report = json.loads(raw)
    if report['source_task_sha256'] != source_sha:
        raise ValueError('Replay lineage mismatch')
    inherited = len(report['calls'])
    previous_limit = report['max_requests']
    output.mkdir(parents=True,exist_ok=False)
    with sqlite3.connect((parent/'snapshot.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as old, sqlite3.connect(output/'snapshot.sqlite') as new:
        old.backup(new)
    report.update(schema='document-verification-continuation-v1',
        parent_report_sha256=hashlib.sha256(raw).hexdigest(),
        parent_task_sha256=hashlib.sha256((parent/'task.json').read_bytes()).hexdigest(),
        parent_max_requests=previous_limit,inherited_requests=inherited,new_request_budget=new_budget,
        max_requests=inherited+new_budget)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('task','database','vectors','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    continuation = parser.add_mutually_exclusive_group()
    continuation.add_argument('--resume', action='store_true')
    continuation.add_argument('--continue-from',type=Path)
    parser.add_argument('--new-request-budget',type=int,choices=range(1,7))
    args = parser.parse_args()
    if bool(args.continue_from) != (args.new_request_budget is not None):
        parser.error('A new budget belongs to --continue-from; --resume cannot enlarge the saved cap')
    key = os.environ['RAG4_EVAL_API_KEY']
    target = args.output.resolve() / 'snapshot.sqlite'
    source_sha = hashlib.sha256(args.task.read_bytes()).hexdigest()
    forked = None
    if args.continue_from:
        forked = fork_checkpoint(args.continue_from,args.output,source_sha,args.new_request_budget)
    elif not args.resume:
        args.output.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as old, sqlite3.connect(target) as new:
            old.backup(new)
    elif not target.is_file():
        parser.error('Resume requires an existing replay checkpoint')
    os.environ['ENV_FILE'] = str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL'] = 'sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI'] = 'false'
    from app.research.tasks import ResearchTask, TaskBudget, comparison_plan
    from app.research.runtime import _load_scope
    from app.research.agent import ResearchAgent
    from app.research.tools import ToolContext
    from app.research.store import SQLResearchTaskStore
    from app.research.model import JsonResearchModel
    from app.services.vector_store import LocalVectorStore
    from app.utils.ids import generate_id
    source = ResearchTask.model_validate_json(args.task.read_text(encoding='utf-8'))
    store = SQLResearchTaskStore()
    vectors = LocalVectorStore(str(args.vectors))
    if args.resume or forked is not None:
        report = forked if forked is not None else json.loads((args.output/'report.json').read_text(encoding='utf-8'))
        if report['source_task_sha256'] != source_sha:
            raise ValueError('Replay lineage mismatch')
        task = store.load(source.user_id, report['task_id'])
        if forked is not None and task != ResearchTask.model_validate_json((args.continue_from/'task.json').read_text(encoding='utf-8')):
            raise ValueError('Parent JSON and SQL checkpoint differ')
        report.setdefault('prior_attempts', []).append({k:report.get(k) for k in
            ('status','attempt_elapsed_ms','batch_documents','model_calls_reserved','tool_calls_reserved')})
    else:
        plan = comparison_plan(source.sources, source.goal, version='research-comparison-v2')
        previous = {s.id:s for s in source.steps}
        steps = []
        for step in plan:
            if step.tool_name in {'search_evidence','compare_evidence'}:
                old = previous[step.id]
                if old.status != 'succeeded':raise ValueError('Only completed extraction checkpoints may be reused')
                steps.append(old)
            else:steps.append(step)
        task = source.model_copy(update={'id': generate_id('research'), 'schema_version':'research-comparison-v2',
            'status':'pending', 'revision':0, 'steps':tuple(steps), 'model_calls_used':0, 'tool_calls_used':0,
            'verification':None, 'verification_batches':(), 'artifact':None, 'error_code':None,
            'completion':source.completion.model_copy(update={'verification_protocol':'source-handles-v4','max_output_tokens':4096}),
            'budget':TaskBudget(max_steps=3*len(source.sources)+4, max_model_calls=2*len(source.sources)+2)})
        task = store.create(task)
        report = {'schema':'document-verification-replay-v1','task_id':task.id,'source_task_sha256':source_sha,
            'reused_search_and_analysis_steps':2*len(source.sources),'source_model_calls_reserved':source.model_calls_used,
            'max_requests':len(source.sources)+1,'calls':[], 'annotation_status':'machine_review_only',
            'quality_gate_passed':False,'business_database_modified':False,
            'completion':task.completion.model_dump(mode='json'),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (Path(__file__).resolve().parents[1]/'app/research').glob('*.py')}}
    models = []
    prior_calls = list(report['calls'])
    report.setdefault('execution_fingerprints',[]).append({
        'requests_before':len(prior_calls),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'research_source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__).resolve().parents[1]/'app/research').glob('*.py')}})
    started = perf_counter()
    def context(current):
        def fresh():
            corpus, bindings, _ = _load_scope(current.user_id, current.index_version_id,
                tuple(s.document_id for s in current.sources), vectors)
            if bindings != current.sources or corpus.corpus_id != current.corpus_id:
                raise ValueError('Source snapshot mismatch')
            return corpus
        corpus = fresh()
        model = JsonResearchModel(current.completion, api_key=key, max_calls=1)
        step = next(s for s in current.steps if s.status == 'running')
        models.append((model, step.arguments.get('document_id')))
        return ToolContext(current, corpus, None, model, fresh)
    def save():
        report.update(calls=prior_calls+[{**c,'document_id':document} for m,document in models for c in m.calls], task_status=task.status,
            tool_calls_reserved=task.tool_calls_used, model_calls_reserved=task.model_calls_used,
            batch_documents=[b.document_id for b in task.verification_batches],
            attempt_elapsed_ms=round((perf_counter()-started)*1000))
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'task.json').write_text(task.model_dump_json(indent=2),encoding='utf-8')
    agent = ResearchAgent(store, context)
    try:
        report['status'] = 'running'
        save()
        if (args.resume or forked is not None) and task.status in {'failed','paused'}:
            task = agent.control(task.user_id,task.id,'resume',task.revision)
        for _ in range(len(task.steps)):
            if task.status in {'completed','failed','cancelled','paused'}:break
            next_step = next(s for s in task.steps if s.status=='pending')
            if next_step.tool_name=='verify_document' and len(report['calls'])>=report['max_requests']:
                report['status']='request_cap_exhausted';break
            task = agent.step(task.user_id, task.id)
            save()
            print(json.dumps({'task_status':task.status,'batches':len(task.verification_batches),'requests':len(report['calls'])}),flush=True)
        if report['status']=='running':report['status']='succeeded' if task.status=='completed' else 'failed'
        if task.artifact:
            report.update(supported=task.verification.supported,total=task.verification.total,
                artifact_id=task.artifact.artifact_id,knowledge_gaps=len(task.artifact.knowledge_gaps))
            (args.output/'artifact.json').write_text(task.artifact.model_dump_json(indent=2),encoding='utf-8')
            (args.output/'comparison.md').write_text(task.artifact.markdown,encoding='utf-8')
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
    finally:save()
    print(json.dumps({'status':report['status'],'requests':len(report['calls']),'batches':len(task.verification_batches)}))
    return 0 if report['status']=='succeeded' else 1


if __name__=='__main__':
    raise SystemExit(main())
