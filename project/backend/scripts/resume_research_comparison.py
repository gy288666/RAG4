"""One explicit network recovery in a NEW SQLite copy, within the task budget.

Only a last failed verify_document step is eligible. Successful extraction and
document reports are reused unchanged; no queries, rebuilds or hidden retries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def require_recoverable(task):
    """Reject semantic/schema failures and plans that need other paid steps."""
    failed=[s for s in task.steps if s.status=='failed']
    if (task.schema_version!='research-comparison-v2' or task.status!='failed' or len(failed)!=1
            or failed[0].tool_name!='verify_document' or any(s.status=='running' for s in task.steps)):
        raise ValueError('Only one failed document verification is recoverable')
    if failed[0].result is None or failed[0].result.error_type not in {'ReadTimeout','ConnectTimeout','ConnectError'}:
        raise ValueError('Explicit recovery is limited to network failures')
    if any(s.status=='pending' and s.tool_name not in {'merge_verification','compose_artifact'} for s in task.steps):
        raise ValueError('Other paid steps remain pending')
    retained={b.document_id for b in task.verification_batches}
    if retained!={s.document_id for s in task.sources}-{failed[0].arguments.get('document_id')}:
        raise ValueError('Successful document checkpoints are incomplete')
    for batch in task.verification_batches:batch.validate_scope(task)
    if task.model_calls_used>=task.budget.max_model_calls or task.tool_calls_used+3>task.budget.max_steps:
        raise ValueError('Original task budget cannot cover recovery and composition')
    return failed[0].id


def copy_database(source,destination):
    if destination.exists():raise FileExistsError('Recovery output already exists')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(destination) as new:
        old.backup(new)


def credential_base(spec):
    """A checkpoint is data, never authority to redirect the provider key."""
    approved='https://api.siliconflow.cn/v1'
    if spec.endpoint!=approved+'/chat/completions':
        raise ValueError('Recovery checkpoint differs from approved SiliconFlow credential binding')
    return approved


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    key=os.environ['RAG4_EVAL_API_KEY']
    parent_raw=(args.source_run/'report.json').read_bytes()
    task_raw=(args.source_run/'task.json').read_bytes()
    parent=json.loads(parent_raw)
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output.resolve()/'research.sqlite'
    copy_database(args.source_run/'research.sqlite',target)
    os.environ['ENV_FILE']=str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI']='false'
    from app.research.tasks import ResearchTask
    from app.research import runtime
    from app.research.model import JsonResearchModel
    from app.research.store import SQLResearchTaskStore
    from app.services.vector_store import LocalVectorStore
    source=ResearchTask.model_validate_json(task_raw)
    failed_step=require_recoverable(source)
    base=credential_base(source.completion)
    store=SQLResearchTaskStore();task=store.load(source.user_id,source.id)
    if task!=source:raise ValueError('Parent SQL and JSON checkpoints differ')
    vector_root=Path(parent.get('vector_store_path',str((args.source_run/'vectors').resolve())))
    vectors=LocalVectorStore(str(vector_root))
    def vector_digests():
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in vector_root.glob('*.json')}
    before_vectors=vector_digests()
    config=SimpleNamespace(llm_base_url=base,llm_model=source.completion.model_id,llm_api_key=key,
        embedding_base_url=base,embedding_api_key=key)
    runtime.config_service.load_runtime_config=lambda db:config  # Process-local, never write credentials to SQL.
    models=[]
    def model_factory(*args,**kwargs):
        model=JsonResearchModel(*args,**kwargs)
        models.append(model)
        return model
    runtime.JsonResearchModel=model_factory
    prior_calls=parent.get('completion_calls',[])
    report={'schema_version':'research-comparison-recovery-v1','status':'running','quality_gate_passed':False,
        'parent_report_sha256':hashlib.sha256(parent_raw).hexdigest(),'parent_task_sha256':hashlib.sha256(task_raw).hexdigest(),
        'parent_task_id':source.id,'failed_step':failed_step,'additional_request_limit':1,
        'original_budget':source.budget.model_dump(mode='json'),'completion_calls':prior_calls,
        'embedding_calls':parent.get('embedding_calls',[]),'vector_store_path':str(vector_root),
        'vector_files_sha256':before_vectors,'prior_batch_documents':[b.document_id for b in source.verification_batches],
        'business_database_modified':False,'annotation_status':'machine_review_only',
        'executed_source_sha256':{str(p.relative_to(Path(__file__).resolve().parents[1])).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__).resolve()]+list((Path(__file__).resolve().parents[1]/'app/research').glob('*.py'))}}
    def save():
        report.update(task_status=task.status,model_calls_reserved=task.model_calls_used,tool_calls_used=task.tool_calls_used,
            completion_calls=prior_calls+[c for m in models for c in m.calls],steps=[s.model_dump(mode='json') for s in task.steps])
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'task.json').write_text(task.model_dump_json(indent=2),encoding='utf-8')
    save()
    agent=runtime.configured_agent(vector_store=vectors,task_store=store)
    try:
        task=agent.control(task.user_id,task.id,'resume',task.revision)
        for _ in range(3):
            if task.status in {'completed','failed','paused','cancelled'}:break
            pending=next(s for s in task.steps if s.status=='pending')
            if pending.tool_name=='verify_document' and sum(len(m.calls) for m in models)>=1:
                raise ValueError('Explicit recovery request limit reached')
            task=agent.step(task.user_id,task.id);save()
            print(json.dumps({'status':task.status,'tools':task.tool_calls_used,'new_requests':sum(len(m.calls) for m in models)}),flush=True)
        if task.verification_batches[:len(source.verification_batches)]!=source.verification_batches:
            raise ValueError('Successful parent reports changed')
        if before_vectors!=vector_digests():raise ValueError('Retained vectors changed')
        report['status']='succeeded' if task.status=='completed' else 'failed'
        report['successful_parent_batches_unchanged']=True
        if task.artifact:
            (args.output/'artifact.json').write_text(task.artifact.model_dump_json(indent=2),encoding='utf-8')
            (args.output/'comparison.md').write_text(task.artifact.markdown,encoding='utf-8')
            report.update(artifact_id=task.artifact.artifact_id,verification=task.verification.model_dump(mode='json'),
                knowledge_gaps=task.artifact.knowledge_gaps,cells=[r.model_dump(mode='json') for r in task.artifact.rows])
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
    finally:save()
    print(json.dumps({'status':report['status'],'new_requests':sum(len(m.calls) for m in models)}))
    return 0 if report['status']=='succeeded' else 2


if __name__=='__main__':
    raise SystemExit(main())
