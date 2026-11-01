"""Durable per-document verification, not hidden retries inside one tool."""
import pytest

from app.research.agent import ResearchAgent, validate_task_plan
from app.research.tasks import TaskBudget, comparison_plan
from app.research.store import SQLResearchTaskStore
from test_research_agent import workflow, finish


@pytest.mark.parametrize('context_policy',['cited-chunk-v1','preceding-children-v1'])
def test_facet_protocol_batches_merge_and_reload_without_losing_assessments(workflow,context_policy):
    from test_verification_facets import FacetModel
    task,*rest=workflow
    task=task.model_copy(update={'completion':task.completion.model_copy(update={
        'verification_protocol':'facet-handles-v5','verification_context_policy':context_policy})})
    task,_,store,model,agent,_=batched((task,*rest))
    original=model.generate
    def routed(operation,payload):
        if operation=='verify_facets':
            model.calls.append({'operation':operation,'status':'succeeded'})
            return FacetModel().generate(operation,payload)
        return original(operation,payload)
    model.verification_protocol='facet-handles-v5'
    model.verification_context_policy=context_policy
    model.generate=routed
    done=finish(agent,task)
    assert done.status=='completed'
    assert len(done.verification_batches)==3
    assert done.verification.verifier_version=='exact-facet-handles-v5'
    assert len(done.verification.assessments)==3
    assert done.verification.context_policy==context_policy
    assert len(done.verification.contexts)==(3 if context_policy=='preceding-children-v1' else 0)
    assert store.load(done.user_id,done.id).artifact==done.artifact


def batched(workflow):
    task, corpus, store, model, _, context = workflow
    task = task.model_copy(update={'id': 'research-batched', 'schema_version': 'research-comparison-v2',
        'budget': TaskBudget(max_steps=14),
        'steps': comparison_plan(task.sources, task.goal, version='research-comparison-v2')})
    store.create(task)
    return task, corpus, store, model, ResearchAgent(store, context), context


def test_document_batches_complete_and_only_then_merge(workflow):
    task, _, store, model, agent, context = batched(workflow)
    for _ in range(7):task = agent.step(task.user_id, task.id)
    assert len(task.verification_batches) == 1 and task.verification is None
    assert task.verification_batches[0].document_id == 'd0'
    assert len(model.calls[-1]['operation']) > 0
    done = finish(ResearchAgent(SQLResearchTaskStore(), context), task)
    assert done.status == 'completed'
    assert done.tool_calls_used == 11 and done.model_calls_used == 6
    assert len(done.verification_batches) == 3 and done.verification.total == 3
    assert done.artifact.verification == done.verification
    assert store.load(done.user_id, done.id).verification_batches == done.verification_batches


def test_failed_second_batch_retains_first_and_resume_does_not_repeat_it(workflow):
    task, _, store, model, agent, context = batched(workflow)
    generate = model.generate
    failed_once = False
    verified_docs = []
    def flaky(operation, payload):
        nonlocal failed_once
        if operation == 'verify':
            documents = {c['document_id'] for c in payload['claims']}
            assert len(documents) == 1
            document = next(iter(documents))
            verified_docs.append(document)
            if document == 'd1' and not failed_once:
                failed_once = True
                model.calls.append({'operation': operation, 'status': 'failed', 'error_type': 'ReadTimeout'})
                raise TimeoutError('provider timeout')
        return generate(operation, payload)
    model.generate = flaky
    failed = finish(agent, task)
    assert failed.status == 'failed' and len(failed.verification_batches) == 1
    assert failed.verification is None and failed.artifact is None
    assert failed.steps[7].result.model_calls[0]['status'] == 'failed'
    resumed = agent.control(failed.user_id, failed.id, 'resume', failed.revision)
    done = finish(ResearchAgent(store, context), resumed)
    assert done.status == 'completed' and done.model_calls_used == 7
    assert verified_docs == ['d0', 'd1', 'd1', 'd2']
    assert len({b.document_id for b in done.verification_batches}) == 3


def test_pause_between_batches_keeps_completed_report(workflow):
    task, _, _, _, agent, _ = batched(workflow)
    for _ in range(7):task = agent.step(task.user_id, task.id)
    paused = agent.control(task.user_id, task.id, 'pause', task.revision)
    assert agent.step(task.user_id, task.id) == paused
    resumed = agent.control(task.user_id, task.id, 'resume', paused.revision)
    done = finish(agent, resumed)
    assert done.status == 'completed' and done.model_calls_used == 6


def test_plan_admission_rejects_budget_for_old_four_call_plan(workflow):
    task, *_ = batched(workflow)
    too_small = task.model_copy(update={'budget': TaskBudget(max_model_calls=4)})
    with pytest.raises(ValueError, match='Budget'):
        validate_task_plan(too_small)


def test_merge_requires_all_batches_and_does_not_call_model(workflow):
    from app.research.tools import comparison_tools
    task, _, _, model, _, context = batched(workflow)
    result = comparison_tools().execute('merge_verification',context(task),{})
    assert result.status=='failed' and not model.calls


def test_batch_cannot_be_reassigned_to_another_document(workflow):
    task, _, _, _, agent, _ = batched(workflow)
    for _ in range(7):task = agent.step(task.user_id,task.id)
    batch = task.verification_batches[0].model_copy(update={'document_id':'d1'})
    with pytest.raises(ValueError,match='scope'):
        batch.validate_scope(task)


def test_over_four_claims_fails_before_provider_call(workflow):
    from app.research.tools import comparison_tools
    task, corpus, _, model, agent, context = batched(workflow)
    for _ in range(6):task = agent.step(task.user_id,task.id)
    original = next(c for c in task.claims if c.document_id=='d0')
    claims = []
    for n in range(5):
        claim = original.model_copy(update={'statement':f'variant{n}'})
        claims.append(claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)}))
    task = task.model_copy(update={'claims':tuple(claims)})
    before = len(model.calls)
    result = comparison_tools().execute('verify_document',context(task),{'document_id':'d0'})
    assert result.status=='failed' and len(model.calls)==before
