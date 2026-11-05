"""Contract and frozen-observation tests; mocked responses are not semantic evals."""
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.research.model import CompletionSpec, JsonResearchModel, PROMPTS, prompt_for
from scripts.evaluate_claim_audit import cases_for, score


def spec(version='research-operator-v1', protocol='facet-handles-v5'):
    return CompletionSpec(endpoint='https://example.test/v1/chat/completions', model_id='test',
                          version=version, verification_protocol=protocol)


def test_old_operator_preserves_all_prompts_and_wire_identity():
    source = spec()
    for operation, original in PROMPTS.items():
        assert prompt_for(source, operation) == original
    assert CompletionSpec.model_validate_json(source.model_dump_json()) == source
    assert prompt_for(spec('custom-historical-version'), 'verify_facets') == PROMPTS['verify_facets']


def test_opt_in_changes_only_facet_prompt_and_rejects_incompatible_protocol():
    revised = spec('research-facet-audit-v2')
    assert prompt_for(revised, 'verify_facets') != PROMPTS['verify_facets']
    for operation in PROMPTS.keys()-{'verify_facets'}:
        assert prompt_for(revised, operation) == PROMPTS[operation]
    with pytest.raises(ValidationError, match='Facet audit'):
        spec('research-facet-audit-v2', 'source-handles-v4')


@pytest.mark.parametrize('version', ['research-operator-v1', 'research-facet-audit-v2'])
def test_http_ledger_binds_actual_prompt_without_extra_requests(version):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"assessments":[]}'}}]})
    source = spec(version)
    model = JsonResearchModel(source, api_key='unit-test', max_calls=1, transport=httpx.MockTransport(respond))
    assert model.generate('verify_facets', {'claims': []}) == {'assessments': []}
    prompt = requests[0]['messages'][0]['content']
    assert prompt == prompt_for(source, 'verify_facets')
    assert model.calls[0]['prompt_sha256'] == hashlib.sha256(prompt.encode()).hexdigest()
    assert model.calls[0]['version'] == version
    with pytest.raises(RuntimeError, match='budget'):
        model.generate('verify_facets', {})
    assert len(requests) == 1


@pytest.fixture
def frozen():
    return json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/research_context_e2e_20261101.json').read_text(encoding='utf-8'))


def test_frozen_r33_signal_catches_actual_wrong_acceptances_and_rejections(frozen):
    cases = cases_for(frozen)
    result = score(cases, frozen['artifact']['verification'])
    assert result['matched'] == 0 and result['total'] == 4
    assert result['quality_gate_passed'] is False
    assert [r['actual'] for r in result['rows']] == ['supported', 'supported', 'insufficient', 'insufficient']
    assert cases == cases_for({'claims': frozen['claims']})


def test_diagnostic_rejects_ambiguous_claim_selection(frozen):
    with pytest.raises(ValueError, match='exactly one'):
        cases_for({'claims': frozen['claims']+frozen['claims']})


def test_invalid_support_id_rejection_cannot_be_counted_as_semantic_success(frozen):
    case = cases_for(frozen)[1]
    report = json.loads(json.dumps(frozen['artifact']['verification']))
    cid = case['claim']['claim_id']
    for verdict in report['verdicts']:
        if verdict['claim_id'] == cid:
            verdict.update(status='insufficient', reason='invalid support handle')
    report['supported'] -= 1
    assessment = next(a for a in report['assessments'] if a['claim_id'] == cid)
    assessment['conditions'].update(status='insufficient', reason='unknown_support_id_or_invalid_span: copied invalid ID', support_quote='')
    result = score([case], report)
    assert result['matched'] == 1
    assert result['semantic_matched'] == 0
    assert result['rows'][0]['invalid_support_checks'] == ['conditions']


def test_cli_revision_is_explicit_and_requires_v5():
    from scripts.evaluate_research_comparison import parse_options, completion_for
    argv = ['--pilot', 'pilot', '--sources', 'sources', '--cached-run', 'cache',
            '--cached-report-sha256', 'f'*64, '--output', 'new']
    assert completion_for(parse_options(argv)).version == 'research-operator-v1'
    with pytest.raises(ValidationError):
        completion_for(parse_options(argv+['--operator-version', 'research-facet-audit-v2']))
    revised = completion_for(parse_options(argv+['--operator-version', 'research-facet-audit-v2',
                                                '--verification-protocol', 'facet-handles-v5']))
    assert revised.version == 'research-facet-audit-v2'
