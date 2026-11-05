"""A failed document can only become an explicit gap, without more model use."""
import pytest
from app.research.artifacts import ArtifactComposer
from scripts.export_research_partial import partial_verification
from test_research_verification_batches import batched
from test_research_agent import workflow


@pytest.fixture(params=['model-only-v1','explicit-row-v1'])
def failed_checkpoint(workflow,request):
    task,*rest=workflow
    policy=request.param
    task=task.model_copy(update={'completion':task.completion.model_copy(update={'result_condition_policy':policy})})
    task,corpus,store,model,agent,_=batched((task,*rest))
    model.result_condition_policy=policy
    original=model.generate
    def generate(operation,payload):
        if operation=='verify' and payload['claims'][0]['document_id']=='d2':
            raise ValueError('controlled invalid document judgment')
        result=original(operation,payload)
        if operation=='extract':
            for claim in result['claims']:claim['facet']='result'
        return result
    model.generate=generate
    for _ in range(9):task=agent.step(task.user_id,task.id)
    assert task.status=='failed' and len(task.verification_batches)==2
    return task,corpus,store,model


def test_partial_export_reuses_successes_and_never_promotes_unverified_result(failed_checkpoint):
    task,corpus,store,model=failed_checkpoint
    calls=len(model.calls)
    report=partial_verification(task,corpus)
    assert len(model.calls)==calls
    assert report.supported==2 and report.total==3
    assert report.verdicts[:2]==tuple(v for b in task.verification_batches for v in b.verification.verdicts)
    assert report.verdicts[-1].status=='insufficient'
    assert report.verdicts[-1].reason=='document_verification_unavailable_after_task_failure'
    if task.completion.result_condition_policy=='explicit-row-v1':
        assert len(report.condition_audits)==3 and all(a.status=='not_applicable' for a in report.condition_audits)
    artifact=ArtifactComposer().compose(corpus,task.goal,tuple(s.document_id for s in task.sources),
        {s.document_id:s.title for s in task.sources},task.claims,report)
    assert len(artifact.citations)==2 and artifact.completion_status=='partial'
    assert task==store.load(task.user_id,task.id) and task.artifact is None
    assert task.status=='failed' and 'not_a_completed_research_task' in report.warnings


@pytest.mark.parametrize('mutation',['completed','corpus','source','duplicate_batches'])
def test_partial_export_rejects_changed_scope_or_input(failed_checkpoint,mutation):
    task,corpus,_,_=failed_checkpoint
    if mutation=='completed':task=task.model_copy(update={'status':'completed'})
    elif mutation=='corpus':task=task.model_copy(update={'corpus_id':'foreign'})
    elif mutation=='duplicate_batches':task=task.model_copy(update={'verification_batches':task.verification_batches*2})
    else:
        claim=task.claims[-1]
        bad=claim.model_copy(update={'citation':claim.citation.model_copy(update={'quote':'invented'})})
        task=task.model_copy(update={'claims':task.claims[:-1]+(bad,)})
    with pytest.raises(ValueError):partial_verification(task,corpus)
