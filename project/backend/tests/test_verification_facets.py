"""Facet policy routing is tested independently of model semantic accuracy."""
import pytest
from app.research.artifacts import EvidenceVerifier, ArtifactComposer, ComparisonArtifact
from app.research.model import CompletionSpec
from test_research_verification_checks import example


class FacetModel:
    verification_protocol = 'facet-handles-v5'

    def __init__(self, failed=None, foreign=False):
        self.failed, self.foreign = failed, foreign
        self.payload = None

    def generate(self, operation, payload):
        assert operation == 'verify_facets'
        self.payload = payload
        return {'assessments': [{'claim_id':c['claim_id'], **{
            name:{'status':'insufficient' if name==self.failed else 'supported',
                'reason':'Test semantic response, not a quality label',
                'support_ids':['foreign' if self.foreign else c['sources'][0]['source_id']]}
            for name in ('attribution','conditions','entailment')}} for c in payload['claims']]}


@pytest.mark.parametrize('facet,rule', [('method','method_scope'),('dataset','dataset_scope'),
    ('result','experiment_conditions'),('limitation','explicit_limitation_scope')])
def test_facet_policy_is_server_selected_and_artifact_roundtrips(facet,rule):
    corpus,original = example()
    claim = original.model_copy(update={'facet':facet})
    claim = claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
    model=FacetModel()
    report=EvidenceVerifier(model).verify(corpus,(claim,))
    assert report.verifier_version=='exact-facet-handles-v5'
    assert model.payload['claims'][0]['requirements']['condition_rule']==rule
    assert model.payload['claims'][0]['requirements']['version']=='facet-scope-v1'
    assert report.supported==1
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'Paper'},(claim,),report)
    restored=ComparisonArtifact.model_validate_json(artifact.model_dump_json())
    assert restored.artifact_id==artifact.artifact_id==restored.expected_id()


@pytest.mark.parametrize('failed',['attribution','conditions','entailment'])
def test_facet_policy_never_bypasses_a_failed_check(failed):
    corpus,claim=example()
    report=EvidenceVerifier(FacetModel(failed)).verify(corpus,(claim,))
    assert report.supported==0
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'Paper'},(claim,),report)
    assert not artifact.citations


def test_facet_policy_keeps_exact_source_handle_gate():
    corpus,claim=example()
    assert EvidenceVerifier(FacetModel(foreign=True)).verify(corpus,(claim,)).supported==0


def test_new_protocol_is_explicit_and_old_default_is_retained():
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test')
    assert spec.verification_protocol=='numeric-model-v2'
    assert CompletionSpec(**{**spec.model_dump(),'verification_protocol':'facet-handles-v5'}).verification_protocol=='facet-handles-v5'


def test_http_wire_uses_versioned_prompt_and_keeps_finite_call_ledger():
    import json
    import httpx
    from app.research.model import JsonResearchModel
    corpus,claim=example()
    def respond(request):
        body=json.loads(request.content)
        assert 'requirements.condition_rule' in body['messages'][0]['content']
        payload=json.loads(body['messages'][1]['content'])
        assert payload['claims'][0]['requirements']['condition_rule']=='experiment_conditions'
        model=FacetModel()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
            'content':json.dumps(model.generate('verify_facets',payload))}}],
            'usage':{'total_tokens':42}})
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test',
        verification_protocol='facet-handles-v5')
    model=JsonResearchModel(spec,api_key='unit-test',max_calls=1,transport=httpx.MockTransport(respond))
    assert EvidenceVerifier(model).verify(corpus,(claim,)).supported==1
    assert model.calls[0]['verification_protocol']=='facet-handles-v5'
    assert model.calls[0]['usage']['total_tokens']==42
    with pytest.raises(RuntimeError,match='budget'):model.generate('verify_facets',{})


def test_failed_verdict_does_not_hide_incorrect_entailment_in_diagnostics():
    from scripts.evaluate_verification_facets import outcome
    corpus,claim=example()
    report=EvidenceVerifier(FacetModel(failed='conditions')).verify(corpus,(claim,))
    row=outcome({'case_id':'compound','claim':claim,'expected':'not_supported',
        'required_checks':{'entailment':'not_supported'}},report)
    assert row['verdict_matches'] is True and row['checks_match'] is False


def test_composer_rechecks_facet_handle_mapping():
    corpus,claim=example()
    report=EvidenceVerifier(FacetModel()).verify(corpus,(claim,))
    assessment=report.assessments[0]
    forged=assessment.model_copy(update={'conditions':assessment.conditions.model_copy(update={'support_ids':('foreign',)})})
    with pytest.raises(ValueError,match='source checks'):
        ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'Paper'},(claim,),
            report.model_copy(update={'assessments':(forged,)}))
