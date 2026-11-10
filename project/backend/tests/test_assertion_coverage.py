"""Coverage/publication contracts; fixture judgments are not semantic gold."""
import json
import httpx
import pytest
from app.research.artifacts import EvidenceVerifier, verification_sources
from app.research.assertions import (build_assertion_plan, AssertionPlan, AssertionReview,
    AssertionCoverageVerifier, compose_assertion_review, AssertionPublication)
from app.research.model import CompletionSpec, JsonResearchModel
from app.research.protocol import ResponseSchemaError
from test_research_verification_checks import example
from test_verification_facets import FacetModel


@pytest.fixture
def covered():
    corpus,claim=example()
    claim=claim.model_copy(update={'facet':'method','statement':'REALM improves prediction，and trains the retriever.'})
    claim=claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
    cut=claim.statement.index('，')+1
    return corpus,claim,build_assertion_plan(corpus,claim,(cut,len(claim.statement)))


class AtomicModel:
    verification_protocol='facet-handles-v5'
    verification_context_policy='preceding-children-v1'
    def __init__(self, statuses=('supported','insufficient')):
        self.statuses,self.calls=statuses,[]
    def generate(self,operation,payload):
        assert operation=='verify_assertions'
        self.calls.append(payload)
        return {'assessments':[{'assertion_id':a['assertion_id'],**{
            name:{'status':self.statuses[i], 'reason':'Fixture response, not semantic acceptance',
                  'support_ids':[item['sources'][0]['source_id']] if self.statuses[i]!='insufficient' else []}
            for name in ('attribution','conditions','entailment')}}
            for item in payload['claims'] for i,a in enumerate(item['assertions'])]}


def test_complete_unicode_ranges_and_stable_versioned_identity(covered):
    corpus,claim,plan=covered
    plan.validate_source(corpus,claim)
    assert ''.join(a.text for a in plan.assertions)==claim.statement
    assert plan==build_assertion_plan(corpus,claim,tuple(a.char_end for a in plan.assertions))
    assert AssertionPlan.model_validate_json(plan.model_dump_json())==plan
    assert len({a.assertion_id for a in plan.assertions})==2


@pytest.mark.parametrize('ends',[(1,), (0,50), (True,50), (30,20,50), (), (10000,)])
def test_invalid_or_incomplete_boundaries_rejected(covered,ends):
    corpus,claim,_=covered
    with pytest.raises(ValueError):build_assertion_plan(corpus,claim,ends)


def test_one_request_keeps_original_statement_and_source_catalog(covered):
    corpus,claim,plan=covered;model=AtomicModel()
    review,=AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert len(model.calls)==1
    item=model.calls[0]['claims'][0]
    assert item['statement']==claim.statement and item['sources']==verification_sources(claim)
    assert item['assertions']==[a.model_dump(mode='json') for a in plan.assertions]
    assert review.verdict(claim).status=='insufficient'
    review.validate_source(corpus,claim)
    assert AssertionReview.model_validate_json(review.model_dump_json())==review


def test_atomic_rejection_blocks_old_compound_acceptance_at_publication(covered):
    corpus,claim,plan=covered
    baseline=EvidenceVerifier(FacetModel()).verify(corpus,(claim,))
    assert baseline.supported==1
    reviews=AssertionCoverageVerifier(AtomicModel()).verify(corpus,(claim,),(plan,))
    publication=compose_assertion_review(corpus,'goal',('d0',),{'d0':'paper'},(claim,),baseline,reviews)
    assert publication.artifact.verification.supported==0
    assert not publication.artifact.citations
    assert publication.baseline==baseline and baseline.supported==1
    publication.validate_source(corpus,(claim,))
    assert AssertionPublication.model_validate_json(publication.model_dump_json())==publication


def test_missing_assertion_judgment_fails_closed(covered):
    corpus,claim,plan=covered;model=AtomicModel(('supported','supported'));generate=model.generate
    model.generate=lambda op,payload:{'assessments':generate(op,payload)['assessments'][:1]}
    review,=AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert review.verdict(claim).status=='insufficient'


def test_all_supported_never_promotes_a_rejected_baseline(covered):
    corpus,claim,plan=covered
    baseline=EvidenceVerifier(FacetModel(failed='entailment')).verify(corpus,(claim,))
    reviews=AssertionCoverageVerifier(AtomicModel(('supported','supported'))).verify(corpus,(claim,),(plan,))
    publication=compose_assertion_review(corpus,'goal',('d0',),{'d0':'paper'},(claim,),baseline,reviews)
    assert publication.artifact.verification.supported==0


def test_real_http_adapter_uses_one_budget_reservation(covered):
    corpus,claim,plan=covered;requests=[]
    def response(request):
        body=json.loads(request.content);requests.append(body)
        payload=json.loads(body['messages'][1]['content'])
        result=AtomicModel().generate('verify_assertions',payload)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]})
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='fixture',
        verification_protocol='facet-handles-v5',verification_context_policy='preceding-children-v1')
    model=JsonResearchModel(spec,api_key='unit-test',max_calls=1,transport=httpx.MockTransport(response))
    AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert len(requests)==len(model.calls)==1
    assert model.calls[0]['assertion_protocol']=='statement-ranges-v1'
    with pytest.raises(RuntimeError):AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert len(requests)==1


@pytest.mark.parametrize('mutation',['gap','overlap','text','version','claim','id'])
def test_plan_forgery_is_rejected_before_any_model_call(covered,mutation):
    corpus,claim,plan=covered;first=plan.assertions[0]
    if mutation=='gap':plan=plan.model_copy(update={'assertions':(first.model_copy(update={'char_end':first.char_end-1}),*plan.assertions[1:])})
    if mutation=='overlap':plan=plan.model_copy(update={'assertions':(first.model_copy(update={'char_end':first.char_end+1}),*plan.assertions[1:])})
    if mutation=='text':plan=plan.model_copy(update={'assertions':(first.model_copy(update={'text':'invented'}),*plan.assertions[1:])})
    if mutation=='version':plan=plan.model_copy(update={'version':'unknown'})
    if mutation=='claim':plan=plan.model_copy(update={'claim_id':'foreign'})
    if mutation=='id':plan=plan.model_copy(update={'plan_id':'forged'})
    model=AtomicModel()
    with pytest.raises(ValueError):AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert not model.calls


@pytest.mark.parametrize('mutation',['duplicate','unknown'])
def test_response_identity_failure_is_safe_and_never_retried(covered,mutation):
    corpus,claim,plan=covered;model=AtomicModel();generate=model.generate
    def altered(operation,payload):
        result=generate(operation,payload)
        if mutation=='duplicate':result['assessments'][1]=result['assessments'][0]
        else:result['assessments'][1]['assertion_id']='PRIVATE_UNTRUSTED_ID'
        return result
    model.generate=altered
    with pytest.raises(ResponseSchemaError) as error:
        AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert 'PRIVATE_UNTRUSTED_ID' not in str(error.value)
    assert len(model.calls)==1


def test_foreign_support_handles_cannot_publish_a_supported_assertion(covered):
    corpus,claim,plan=covered;model=AtomicModel(('supported','supported'));generate=model.generate
    def foreign(operation,payload):
        result=generate(operation,payload)
        for assessment in result['assessments']:
            for name in ('attribution','conditions','entailment'):assessment[name]['support_ids']=['foreign']
        return result
    model.generate=foreign
    review,=AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert review.verdict(claim).status=='insufficient'


def test_full_support_retains_original_statement_and_exact_quote(covered):
    corpus,claim,plan=covered
    baseline=EvidenceVerifier(FacetModel()).verify(corpus,(claim,))
    reviews=AssertionCoverageVerifier(AtomicModel(('supported','supported'))).verify(corpus,(claim,),(plan,))
    publication=compose_assertion_review(corpus,'goal',('d0',),{'d0':'paper'},(claim,),baseline,reviews)
    assert publication.artifact.citations==(claim,)
    assert publication.artifact.rows[0].cells[0].statement==claim.statement
    publication.validate_source(corpus,(claim,))


def test_contradicted_assertion_prevents_compound_support(covered):
    corpus,claim,plan=covered
    review,=AssertionCoverageVerifier(AtomicModel(('supported','contradicted'))).verify(corpus,(claim,),(plan,))
    assert review.verdict(claim).status=='contradicted'


@pytest.mark.parametrize('mutation',['drop_review','alter_artifact','alter_plan','drop_assessment'])
def test_publication_rebuild_detects_tampering_even_with_recomputed_outer_identity(covered,mutation):
    corpus,claim,plan=covered
    baseline=EvidenceVerifier(FacetModel()).verify(corpus,(claim,))
    reviews=AssertionCoverageVerifier(AtomicModel()).verify(corpus,(claim,),(plan,))
    publication=compose_assertion_review(corpus,'goal',('d0',),{'d0':'paper'},(claim,),baseline,reviews)
    if mutation=='drop_review':publication=publication.model_copy(update={'reviews':()})
    if mutation=='alter_artifact':publication=publication.model_copy(update={'artifact':publication.artifact.model_copy(update={'markdown':'forged'})})
    if mutation=='alter_plan':publication=publication.model_copy(update={'reviews':(reviews[0].model_copy(update={'plan':plan.model_copy(update={'statement':'forged'})}),)})
    if mutation=='drop_assessment':publication=publication.model_copy(update={'reviews':(reviews[0].model_copy(update={'assessments':()}),)})
    publication=publication.model_copy(update={'publication_id':publication.expected_id()})
    with pytest.raises(ValueError):publication.validate_source(corpus,(claim,))


def test_model_failure_is_propagated_once_without_hidden_retry(covered):
    corpus,claim,plan=covered;model=AtomicModel()
    def fail(operation,payload):model.calls.append(payload);raise RuntimeError('fixture transport failure')
    model.generate=fail
    with pytest.raises(RuntimeError):AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    assert len(model.calls)==1


def test_multiple_claims_share_one_request_and_have_independent_ids(covered):
    corpus,claim,plan=covered
    other=claim.model_copy(update={'statement':'Another claim，with another scope.'})
    other=other.model_copy(update={'claim_id':other.expected_id(corpus.corpus_id)})
    other_plan=build_assertion_plan(corpus,other,(other.statement.index('，')+1,len(other.statement)))
    model=AtomicModel(('supported','supported'))
    reviews=AssertionCoverageVerifier(model).verify(corpus,(claim,other),(plan,other_plan))
    assert len(model.calls)==1 and len(reviews)==2
    assert {r.plan.claim_id for r in reviews}=={claim.claim_id,other.claim_id}
    assert all(r.verdict(c).status=='supported' for r,c in zip(reviews,(claim,other)))


def test_scope_and_total_assertion_cap_checked_before_call(covered):
    corpus,claim,plan=covered;model=AtomicModel()
    claims=[];plans=[]
    for text in ('abcdefgh','ijklmnop','qrstuvwx'):
        c=claim.model_copy(update={'statement':text})
        c=c.model_copy(update={'claim_id':c.expected_id(corpus.corpus_id)})
        claims.append(c);plans.append(build_assertion_plan(corpus,c,tuple(range(1,9))))
    for selected,partitions in (((),()),((claim,claim),(plan,plan)),((claim,),()),(tuple(claims),tuple(plans))):
        with pytest.raises(ValueError):AssertionCoverageVerifier(model).verify(corpus,selected,partitions)
    assert not model.calls


def test_whitespace_ranges_and_context_free_configuration_rejected(covered):
    corpus,claim,plan=covered
    claim=claim.model_copy(update={'statement':'a b'})
    claim=claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
    with pytest.raises(ValueError):build_assertion_plan(corpus,claim,(1,2,3))
    model=AtomicModel();model.verification_context_policy='cited-chunk-v1'
    with pytest.raises(ValueError):AssertionCoverageVerifier(model).verify(corpus,(covered[1],),(plan,))
    assert not model.calls
