"""Domain/history checks independent of providers and HTTP."""
import json
import pytest
from app.research.claim_reviews import (append_claim_review,build_review_view,validate_review_history,ClaimReviewView)
from app.research.agent import validate_task_plan
from app.research.tasks import ResearchTask
from test_research_agent import workflow,finish


@pytest.fixture
def finished(workflow):
    task,corpus,store,model,agent,_=workflow
    return finish(agent,task),corpus,store,model


def test_legacy_payload_and_identity_round_trip_omit_empty_history(finished):
    task,corpus,_,_=finished
    before=task.model_dump_json()
    assert 'claim_reviews' not in json.loads(before)
    assert ResearchTask.model_validate_json(before).model_dump_json()==before
    view=build_review_view(task,corpus)
    assert view.artifact==task.artifact and view.source_artifact_id==task.artifact.artifact_id
    assert ClaimReviewView.model_validate_json(view.model_dump_json())==view


def test_review_persists_without_budget_or_step_changes_and_terminal_agent_is_inert(finished,workflow):
    task,corpus,store,model=finished
    claim=task.artifact.citations[0]
    changed=append_claim_review(task,claim.claim_id,'withdraw','Not supported by the complete passage.')
    saved=store.save_checkpoint(changed,expected_revision=task.revision)
    assert store.load(task.user_id,task.id)==saved
    assert (saved.steps,saved.model_calls_used,saved.tool_calls_used,saved.artifact)==(task.steps,task.model_calls_used,task.tool_calls_used,task.artifact)
    before=len(model.calls)
    assert workflow[4].step(task.user_id,task.id)==saved and len(model.calls)==before
    assert len(build_review_view(saved,corpus).artifact.citations)==2


@pytest.mark.parametrize('mutation',['claim','actor','artifact','sequence','chain','revision','event_id','time','reason','version'])
def test_history_corruption_rejected_before_storage(finished,mutation):
    task,_,store,_=finished
    reviewed=append_claim_review(task,task.artifact.citations[0].claim_id,'withdraw','Evidence does not cover the statement.')
    event=reviewed.claim_reviews[0]
    change={'claim':{'claim_id':'foreign'},'actor':{'actor_id':task.user_id+1},
            'artifact':{'source_artifact_id':'foreign'},'sequence':{'sequence':2},
            'chain':{'previous_event_id':'foreign'},'revision':{'task_revision':reviewed.revision+1},
            'event_id':{'event_id':'foreign'},'time':{'reviewed_at':'not-a-time'},
            'reason':{'reason':'   '},'version':{'version':'unknown'}}[mutation]
    corrupt=reviewed.model_copy(update={'claim_reviews':(event.model_copy(update=change),)})
    with pytest.raises(ValueError):store.save_checkpoint(corrupt,expected_revision=task.revision)
    assert store.load(task.user_id,task.id)==task


def test_history_limit_preserves_existing_events(finished):
    task,_,_,_=finished
    for _ in range(100):task=append_claim_review(task,task.artifact.citations[0].claim_id,'reset','Explicit return to unreviewed.')
    validate_review_history(task)
    with pytest.raises(ValueError):append_claim_review(task,task.artifact.citations[0].claim_id,'retain','One too many.')
    assert len(task.claim_reviews)==100


def test_withdrawn_claim_is_preserved_as_an_item_and_cannot_promote_other_gaps(finished):
    task,corpus,_,_=finished
    reviewed=append_claim_review(task,task.artifact.citations[0].claim_id,'withdraw','Selected support is incomplete.')
    view=build_review_view(reviewed,corpus)
    assert len(view.items)==3 and view.items[0].review_status=='withdrawn'
    assert view.items[0].claim==task.artifact.citations[0]
    assert len(view.artifact.knowledge_gaps)==len(task.artifact.knowledge_gaps)+1
    assert task.artifact.citations[0].citation.quote==view.items[0].claim.citation.quote
    assert not view.quality_gate_passed


def test_dropping_last_event_or_changing_task_status_cannot_hide_history(finished):
    task,_,_,_=finished
    task=append_claim_review(task,task.artifact.citations[0].claim_id,'withdraw','First decision.')
    task=append_claim_review(task,task.artifact.citations[0].claim_id,'reset','Changed decision.')
    for change in ({'claim_reviews':task.claim_reviews[:-1]},{'status':'pending'}):
        with pytest.raises(ValueError):validate_task_plan(task.model_copy(update=change))


def test_checkpoint_store_cannot_erase_all_committed_review_history(finished):
    task,_,store,_=finished
    reviewed=append_claim_review(task,task.artifact.citations[0].claim_id,'withdraw','Keep this audit event.')
    store.save_checkpoint(reviewed,expected_revision=task.revision)
    with pytest.raises(ValueError):
        store.save_checkpoint(reviewed.model_copy(update={'claim_reviews':()}),expected_revision=reviewed.revision)
    assert store.load(task.user_id,task.id)==reviewed


def test_review_append_cannot_rewrite_completed_task_fields(finished):
    task,_,store,_=finished
    reviewed=append_claim_review(task,task.artifact.citations[0].claim_id,'withdraw','Keep this audit event.')
    with pytest.raises(ValueError):store.save_checkpoint(reviewed.model_copy(update={'error_code':'rewritten'}),expected_revision=task.revision)
    assert store.load(task.user_id,task.id)==task
