"""Strict decoding stays strict; safe metadata must never retain model text."""
import json
import httpx
import pytest
from app.research.model import CompletionSpec,JsonResearchModel


@pytest.mark.parametrize('content,hint',[
    ('```json\n{"private":"PRIVATE_MARKER"}\n```','fenced_prefix'),
    ('Here is PRIVATE_MARKER: {}','other_prefix'),
    ('{"private":"PRIVATE_MARKER",}','object_prefix'),
    ('','empty'),
    ('[] PRIVATE_MARKER','array_prefix'),
])
def test_model_json_failure_has_safe_location_and_format_metadata(content,hint):
    response={'choices':[{'finish_reason':'stop','message':{'content':content}}]}
    model=JsonResearchModel(CompletionSpec(endpoint='https://example.test/completions',model_id='fixture'),
        api_key='TEST_SECRET',max_calls=1,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=response)))
    with pytest.raises(RuntimeError):model.generate('verify',{})
    failure=model.calls[0]['response_error']
    assert failure['stage']=='model_json' and failure['format_hint']==hint
    assert failure['code']=='invalid_json' and failure['chars']==len(content)
    assert isinstance(failure['offset'],int)
    assert 'PRIVATE_MARKER' not in json.dumps(model.calls) and 'TEST_SECRET' not in json.dumps(model.calls)
    assert len(model.calls)==1


def test_provider_json_failure_is_separate_from_model_content():
    model=JsonResearchModel(CompletionSpec(endpoint='https://example.test/completions',model_id='fixture'),
        api_key='TEST_SECRET',max_calls=1,transport=httpx.MockTransport(lambda r:httpx.Response(200,text='PRIVATE_MARKER')))
    with pytest.raises(RuntimeError):model.generate('verify',{})
    assert model.calls[0]['response_error']['stage']=='provider_json'
    assert 'PRIVATE_MARKER' not in json.dumps(model.calls)


@pytest.mark.parametrize('content,code',[
    ('{"PRIVATE_MARKER":1,"PRIVATE_MARKER":2}','duplicate_field'),
    ('[]','non_object'),
    (None,'invalid_input_type'),
])
def test_other_content_contract_failures_remain_rejected(content,code):
    model=JsonResearchModel(CompletionSpec(endpoint='https://example.test/completions',model_id='fixture'),
        api_key='fixture',max_calls=1,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={
            'choices':[{'finish_reason':'stop','message':{'content':content}}]})))
    with pytest.raises(RuntimeError):model.generate('verify',{})
    assert model.calls[0]['response_error']['code']==code
    assert 'PRIVATE_MARKER' not in json.dumps(model.calls)


def test_valid_json_keeps_existing_success_ledger_shape():
    model=JsonResearchModel(CompletionSpec(endpoint='https://example.test/completions',model_id='fixture'),
        api_key='fixture',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={
            'choices':[{'finish_reason':'stop','message':{'content':'{"verdicts":[]}'}}]})))
    assert model.generate('verify',{})=={'verdicts':[]}
    assert 'response_error' not in model.calls[0]
