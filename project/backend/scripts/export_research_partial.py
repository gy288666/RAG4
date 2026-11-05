"""Export a partial draft from a FAILED task, without resuming or model use."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def partial_verification(task,corpus):
    """Compatibility entry point; production logic lives in app.research.partial."""
    from app.research.partial import partial_verification as generate
    return generate(task,corpus)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-run','vectors','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    raw=(args.source_run/'task.json').read_bytes()
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output.resolve()/'snapshot.sqlite'
    with sqlite3.connect((args.source_run/'research.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target) as new:
        old.backup(new)
    os.environ['ENV_FILE']=str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI']='false'
    from app.research.tasks import ResearchTask
    from app.research.store import SQLResearchTaskStore
    from app.research.partial import build_partial_view
    from app.services.vector_store import LocalVectorStore
    from scripts.reverify_research_claims import frozen_corpus
    task=ResearchTask.model_validate_json(raw)
    if SQLResearchTaskStore().load(task.user_id,task.id)!=task:raise ValueError('SQL/JSON checkpoint differs')
    digests=lambda:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.vectors.glob('*.json')}
    before=digests();corpus=frozen_corpus(task,LocalVectorStore(str(args.vectors)))
    view=build_partial_view(task,corpus)
    artifact=view.artifact;verification=artifact.verification
    if before!=digests() or (args.source_run/'task.json').read_bytes()!=raw:raise ValueError('Source changed')
    backend=Path(__file__).resolve().parents[1]
    report={'schema':'failed-research-partial-export-v1','source_task_status':task.status,'source_task_sha256':hashlib.sha256(raw).hexdigest(),
        'quality_gate_passed':False,'annotation_status':'machine_review_only','task_marked_completed':False,
        'artifact_attached_to_task':False,'model_calls':0,'embedding_calls':0,'business_database_accessed':False,
        'retained_documents':[b.document_id for b in task.verification_batches],
        'unverified_documents':sorted({s.document_id for s in task.sources}-{b.document_id for b in task.verification_batches}),
        'verification':verification.model_dump(mode='json'),'artifact':artifact.model_dump(mode='json'),
        'source_inputs_unchanged':True,'vector_sha256':before,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'comparison.md').write_text(view.markdown,encoding='utf-8')
    print(json.dumps({'source_task_status':task.status,'partial_supported':verification.supported,'unverified_documents':report['unverified_documents'],'model_calls':0}))
    return 0


if __name__=='__main__':raise SystemExit(main())
