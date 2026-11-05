"""Return-boundary errors must identify the constraint without logging content."""
import pytest
from app.research.artifacts import EvidenceVerifier
from app.research.protocol import ResponseSchemaError
from app.research.tools import comparison_tools,ToolContext
from test_research_verification_checks import example
from test_verification_facets import FacetModel
from test_research_agent import workflow
from test_research_verification_batches import batched


@pytest.mark.parametrize('protocol',['numeric-model-v2','source-checks-v3','source-handles-v4','facet-handles-v5'])
@pytest.mark.parametrize('mutation',['duplicate','unknown','both'])
def test_all_judge_protocols_expose_safe_identity_counts(protocol,mutation):
    corpus,claim=example()
    class Model:
        verification_protocol=protocol
        def generate(self,operation,payload):
            if protocol=='numeric-model-v2':
                row={'claim_id':claim.claim_id,'status':'supported','reason':'untrusted-private-reason'}
                key='verdicts'
            else:
                key='assessments'
                if protocol=='source-checks-v3':
                    row={'claim_id':claim.claim_id,**{name:{'status':'supported','reason':'untrusted-private-reason','support_quote':claim.citation.quote}
                        for name in ('attribution','conditions','entailment')}}
                else:row=FacetModel().generate('verify_facets',payload)['assessments'][0]
            foreign={**row,'claim_id':'untrusted-private-claim-id'}
            rows=[row,row] if mutation=='duplicate' else [foreign] if mutation=='unknown' else [foreign,foreign]
            return {key:rows}
    with pytest.raises(ResponseSchemaError) as caught:
        EvidenceVerifier(Model()).verify(corpus,(claim,))
    error=caught.value
    assert error.code=={'duplicate':'duplicate_claim_ids','unknown':'unknown_claim_ids','both':'duplicate_and_unknown_claim_ids'}[mutation]
    assert error.counts['expected']==1
    assert error.counts['received']==(1 if mutation=='unknown' else 2)
    assert error.counts['unknown']==(0 if mutation=='duplicate' else 1)
    assert error.counts['missing']==(0 if mutation=='duplicate' else 1)
    assert all('untrusted-private' not in d for d in error.diagnostics)


def test_omitted_judgment_keeps_existing_insufficient_behavior():
    corpus,claim=example()
    model=FacetModel();model.generate=lambda *args:{'assessments':[]}
    report=EvidenceVerifier(model).verify(corpus,(claim,))
    assert report.supported==0 and report.verdicts[0].reason=='judge_did_not_verify_claim'


@pytest.mark.parametrize('mutation,code',[
    ('claim_scope','batch_scope'),('coverage','batch_verdict_coverage'),('counters','batch_counters'),
    ('protocol','batch_protocol'),('policy','batch_policy'),('audit','batch_condition_scope'),
    ('condition_coverage','batch_condition_coverage')])
def test_batch_failure_has_a_distinct_safe_stage(workflow,mutation,code):
    task,_,_,_,agent,_=batched(workflow)
    for _ in range(7):task=agent.step(task.user_id,task.id)
    batch=task.verification_batches[0];report=batch.verification
    if mutation=='claim_scope':batch=batch.model_copy(update={'document_id':'foreign'})
    elif mutation=='coverage':batch=batch.model_copy(update={'verification':report.model_copy(update={'verdicts':()})})
    elif mutation=='counters':batch=batch.model_copy(update={'verification':report.model_copy(update={'supported':0})})
    elif mutation=='protocol':batch=batch.model_copy(update={'verification':report.model_copy(update={'verifier_version':'exact-source-checks-v3'})})
    elif mutation=='policy':batch=batch.model_copy(update={'verification':report.model_copy(update={'result_condition_policy':'explicit-row-v1'})})
    elif mutation=='condition_coverage':
        claim=next(c for c in task.claims if c.document_id==batch.document_id)
        result=claim.model_copy(update={'facet':'result'})
        result=result.model_copy(update={'claim_id':result.expected_id(task.corpus_id)})
        task=task.model_copy(update={'claims':tuple(result if c.claim_id==claim.claim_id else c for c in task.claims),
                                    'completion':task.completion.model_copy(update={'result_condition_policy':'explicit-row-v1'})})
        changed=report.model_copy(update={'result_condition_policy':'explicit-row-v1',
            'verdicts':(report.verdicts[0].model_copy(update={'claim_id':result.claim_id}),)})
        batch=batch.model_copy(update={'claim_ids':(result.claim_id,),'verification':changed})
    else:
        # An invalid audit cannot occur under the old frozen policy.
        from app.research.result_conditions import ResultConditionAudit
        audit=ResultConditionAudit(audit_id='forged',corpus_id=task.corpus_id,claim_id=batch.claim_ids[0],status='unknown',reason='test')
        batch=batch.model_copy(update={'verification':report.model_copy(update={'condition_audits':(audit,)})})
    with pytest.raises(ResponseSchemaError) as caught:batch.validate_scope(task)
    assert caught.value.code==code


def test_unclassified_value_error_is_safe_and_not_mislabeled_as_known_identity_error(workflow,monkeypatch):
    task,corpus,_,model,agent,context=batched(workflow)
    for _ in range(6):task=agent.step(task.user_id,task.id)
    def fail(*args):raise ValueError('untrusted-private-exception')
    monkeypatch.setattr(EvidenceVerifier,'verify',fail)
    result=comparison_tools().execute('verify_document',context(task),{'document_id':'d0'})
    assert result.status=='failed'
    assert any('unclassified_document_validation' in d for d in result.warnings)
    assert 'untrusted-private' not in result.model_dump_json()


def test_identity_diagnostic_survives_tool_and_sql_checkpoint(workflow):
    task,_,store,model,agent,_=batched(workflow)
    for _ in range(6):task=agent.step(task.user_id,task.id)
    model.generate=lambda *args:{'verdicts':[{'claim_id':'untrusted-private-id','status':'supported','reason':'untrusted-private-reason'}]}
    failed=agent.step(task.user_id,task.id)
    result=next(s.result for s in failed.steps if s.status=='failed')
    assert failed.status=='failed' and result.error_type=='ResponseContractError'
    assert 'response_contract_invalid:verify:verdicts:unknown_claim_ids' in result.warnings
    assert any('expected=1' in w and 'unknown=1' in w for w in result.warnings)
    assert 'untrusted-private' not in result.model_dump_json()
    assert store.load(failed.user_id,failed.id)==failed


@pytest.mark.parametrize('mutation',['route','code','count_key','count_type'])
def test_diagnostic_factory_cannot_echo_untrusted_route_or_fields(mutation):
    from app.research.protocol import ResponseContractError
    values={'code':'unknown_claim_ids','operation':'verify','collection':'verdicts','counts':{'expected':1}}
    if mutation=='route':values['operation']='untrusted-private-operation'
    elif mutation=='code':values['code']='untrusted-private-code'
    elif mutation=='count_key':values['counts']={'untrusted-private-key':1}
    else:values['counts']={'expected':'untrusted-private-value'}
    with pytest.raises(ValueError) as caught:ResponseContractError(**values)
    assert 'untrusted-private' not in str(caught.value)


def test_document_probe_rejects_partial_or_cross_document_scope():
    from types import SimpleNamespace
    from scripts.reverify_research_claims import complete_document_scope
    a=SimpleNamespace(document_id='a',claim_id='a1')
    b=SimpleNamespace(document_id='a',claim_id='a2')
    c=SimpleNamespace(document_id='b',claim_id='b1')
    task=SimpleNamespace(claims=(a,b,c))
    assert complete_document_scope(task,(a,b))=='a'
    for claims in ((),(a,),(a,b,c)):
        with pytest.raises(ValueError):complete_document_scope(task,claims)
