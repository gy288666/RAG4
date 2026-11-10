"""List labels stay bounded/owner-scoped without hiding corrupt task metadata."""
import json
import pytest
from app.core.database import SessionLocal
from app.models.research_task import ResearchTaskRecord
from app.research.store import digest
from test_research_agent import workflow


def test_goal_preview_is_owner_scoped_and_does_not_return_checkpoint_body(workflow):
    task,_,store,*_=workflow
    items,total=store.listing(task.user_id)
    assert total==1 and items[0]['goal_preview']==task.goal
    assert set(items[0])=={'id','status','revision','goal_preview'}
    assert store.listing(task.user_id+100)==([],0)
    assert store.load(task.user_id,task.id)==task


@pytest.mark.parametrize('mutation',['hash','owner','broken','long'])
def test_invalid_summary_is_withheld_and_long_goal_is_bounded(workflow,mutation):
    task,_,store,*_=workflow
    with SessionLocal() as db:
        row=db.get(ResearchTaskRecord,task.id)
        data=json.loads(row.payload_json)
        if mutation=='owner':data['user_id']+=1
        if mutation=='long':data['goal']='研究目标'*100
        row.payload_json='broken' if mutation=='broken' else json.dumps(data,ensure_ascii=False)
        if mutation!='hash':row.payload_sha256=digest(row.payload_json)
        else:row.payload_sha256='0'*64
        db.commit()
    items,total=store.listing(task.user_id)
    assert total==1 and items[0]['id']==task.id
    assert items[0]['goal_preview']==('研究目标'*40 if mutation=='long' else None)
