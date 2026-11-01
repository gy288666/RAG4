"""Single-claim comparisons must keep non-treatment model settings fixed."""
import pytest
from pydantic import ValidationError
from app.research.model import CompletionSpec
from scripts.reverify_research_claims import verification_spec


def test_replay_overrides_only_protocol_and_explicit_output_cap():
    source=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test',
        version='frozen-v2',timeout_seconds=23,max_output_tokens=2048,
        extraction_protocol='source-handles-v2',response_format='json_object')
    compared=verification_spec(source,'facet-handles-v5',4096)
    assert compared.model_dump(exclude={'verification_protocol','max_output_tokens'}) == source.model_dump(
        exclude={'verification_protocol','max_output_tokens'})
    assert compared.max_output_tokens==4096 and compared.verification_protocol=='facet-handles-v5'
    assert source.max_output_tokens==2048 and source.verification_protocol=='numeric-model-v2'
    assert verification_spec(source,'source-handles-v4').max_output_tokens==8192


@pytest.mark.parametrize('overrides',[('facet-handles-v5',0),('unknown',4096),('source-handles-v4',True)])
def test_replay_rejects_invalid_override_before_any_provider_call(overrides):
    source=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test')
    with pytest.raises(ValidationError):verification_spec(source,*overrides)


def test_context_override_is_validated_without_mutating_frozen_source():
    source=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test')
    compared=verification_spec(source,'facet-handles-v5',4096,'preceding-children-v1')
    assert compared.verification_context_policy=='preceding-children-v1'
    assert source.verification_context_policy=='cited-chunk-v1'
    with pytest.raises(ValidationError):verification_spec(source,'source-handles-v4',4096,'preceding-children-v1')


@pytest.mark.parametrize('changed',[None,'corpus','bindings'])
def test_replay_source_guard_checks_scope_and_frozen_identity(monkeypatch,changed):
    from types import SimpleNamespace
    from app.research import runtime
    from scripts.reverify_research_claims import frozen_corpus
    sources=(SimpleNamespace(document_id='paper'),)
    task=SimpleNamespace(user_id=7,index_version_id='retained',corpus_id='frozen',sources=sources)
    expected=SimpleNamespace(corpus_id='changed' if changed=='corpus' else 'frozen')
    store=object()
    def load(owner,version,docs,vectors):
        assert (owner,version,docs,vectors)==(7,'retained',('paper',),store)
        return expected,() if changed=='bindings' else sources,None
    monkeypatch.setattr(runtime,'_load_scope',load)
    if changed:
        with pytest.raises(ValueError,match='snapshot'):frozen_corpus(task,store)
    else:assert frozen_corpus(task,store) is expected
