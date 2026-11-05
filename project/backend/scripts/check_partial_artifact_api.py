"""Exercise the partial-view HTTP route on a NEW copy of a real failed run.

Signed test JWTs exist only in memory. This checks authorization and retained
sources, not the production login flow, model quality, or a business migration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-run','vectors','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    raw=(args.source_run/'task.json').read_bytes()
    args.output.mkdir(parents=True,exist_ok=False)
    target=args.output.resolve()/'snapshot.sqlite'
    with sqlite3.connect((args.source_run/'research.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(target) as copy:
        source.backup(copy)
    os.environ['ENV_FILE']=str(args.output.resolve()/'nonexistent.env')
    os.environ['DATABASE_URL']='sqlite:///'+target.as_posix()
    os.environ['DEV_MOCK_AI']='false'
    from fastapi.testclient import TestClient
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.models.user import User
    from app.models.research_task import ResearchTaskRecord
    from app.research import runtime
    from app.research.tasks import ResearchTask
    from app.research.partial import PartialArtifactView
    from app.research.store import SQLResearchTaskStore
    from app.services.vector_store import LocalVectorStore
    from app.services import index_version_service as versions
    task=ResearchTask.model_validate_json(raw)
    if SQLResearchTaskStore().load(task.user_id,task.id)!=task:raise ValueError('SQL/JSON snapshots differ')
    with SessionLocal() as db:
        owner=db.get(User,task.user_id)
        owner_token,_=create_access_token(owner.id,owner.email,owner.role,owner.token_version or 0)
        other=User(email='partial-api-other@example.invalid',password_hash='not-a-login',status=1)
        db.add(other);db.commit();db.refresh(other)
        other_token,_=create_access_token(other.id,other.email,other.role,other.token_version or 0)
    def row_state():
        with SessionLocal() as db:
            row=db.get(ResearchTaskRecord,task.id)
            return row.payload_json,row.payload_sha256,row.status,row.revision
    def forbidden(*args,**kwargs):raise AssertionError('Read-only route touched a forbidden execution dependency')
    runtime.get_vector_store=lambda:LocalVectorStore(str(args.vectors))
    runtime.JsonResearchModel=forbidden
    runtime.RemoteEmbeddingAdapter=forbidden
    runtime.config_service.load_runtime_config=forbidden
    SQLResearchTaskStore.save_checkpoint=forbidden
    versions.switch_version=forbidden
    from app.main import app
    before=row_state();active=versions.active_state(task.user_id)
    digests=lambda:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.vectors.glob('*.json')}
    vectors_before=digests()
    client=TestClient(app)
    url=f'/api/v1/research-tasks/{task.id}/partial-artifact'
    owner_header={'Authorization':'Bearer '+owner_token}
    response=client.get(url,headers=owner_header,params={'expected_revision':task.revision})
    if response.status_code!=200:raise ValueError('Authorized partial view request failed')
    view=PartialArtifactView.model_validate(response.json()['data'])
    if view.view_id!=view.expected_id():raise ValueError('Partial view identity differs')
    statuses={'owner':response.status_code,'anonymous':client.get(url).status_code,
        'other_user':client.get(url,headers={'Authorization':'Bearer '+other_token}).status_code,
        'stale_revision':client.get(url,headers=owner_header,params={'expected_revision':task.revision+1}).status_code}
    if statuses!={'owner':200,'anonymous':401,'other_user':404,'stale_revision':409}:raise ValueError('Authorization/state contract differs')
    repeated=client.get(url,headers=owner_header)
    if repeated.json()['data']['view_id']!=view.view_id:raise ValueError('Repeated read differs')
    if row_state()!=before or versions.active_state(task.user_id)!=active or vectors_before!=digests():
        raise ValueError('Read-only request changed checkpoint, pointer or vectors')
    if (args.source_run/'task.json').read_bytes()!=raw:raise ValueError('Source task changed')
    backend=Path(__file__).resolve().parents[1]
    report={'schema':'partial-artifact-api-check-v1','quality_gate_passed':False,
        'auth_method':'signed_test_jwt_for_isolated_copy_not_production_login','statuses':statuses,
        'view':view.model_dump(mode='json'),'cache_control':response.headers.get('cache-control'),
        'model_calls':0,'embedding_calls':0,'task_unchanged':True,'vectors_unchanged':True,
        'active_pointer_unchanged':True,'source_task_sha256':hashlib.sha256(raw).hexdigest(),
        'business_database_accessed':False,'test_user_created_in_isolated_copy':True,
        'vector_sha256':vectors_before,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'code_sha256':{str(p.relative_to(backend)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [backend/'app/api/v1/research.py']+list((backend/'app/research').glob('*.py'))}}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    client.close()
    print(json.dumps({'statuses':statuses,'supported':view.artifact.verification.supported,'source_task_status':view.source_task_status,'model_calls':0}))
    return 0


if __name__=='__main__':raise SystemExit(main())
