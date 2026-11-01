"""Opt-in pilot settings keep historical defaults and reject unsafe mixtures early."""
import pytest
from pydantic import ValidationError
from scripts.evaluate_research_comparison import parse_options,completion_for


BASE=['--pilot','unused.json','--sources','unused','--cached-run','unused',
    '--cached-report-sha256','0'*64,'--output','unused-new']


def test_pilot_default_settings_preserve_original_behavior():
    args=parse_options(BASE);spec=completion_for(args)
    assert args.plan_version=='research-comparison-v1'
    assert args.context_policy=='parent-floor-v2' and args.candidate_policy=='vector-v1'
    assert spec.max_output_tokens==2048 and spec.verification_protocol=='numeric-model-v2'
    assert 'verification_context_policy' not in spec.model_dump()
    assert args.retry_network_once is False


def test_pilot_can_select_new_bounded_plan_and_verification_context():
    args=parse_options(BASE+['--plan-version','research-comparison-v2','--candidate-policy','source-role-v3',
        '--context-policy','local-window-v3','--verification-protocol','facet-handles-v5',
        '--verification-context-policy','preceding-children-v1','--max-output-tokens','4096'])
    spec=completion_for(args)
    assert args.plan_version=='research-comparison-v2' and args.candidate_policy=='source-role-v3'
    assert spec.verification_context_policy=='preceding-children-v1' and spec.max_output_tokens==4096


def test_invalid_context_combination_is_rejected_without_files_or_credentials():
    args=parse_options(BASE+['--verification-context-policy','preceding-children-v1'])
    with pytest.raises(ValidationError):completion_for(args)


def test_pilot_rejects_bad_combination_before_cache_or_provider_access(monkeypatch,capsys):
    from pathlib import Path
    from scripts import evaluate_research_comparison as pilot
    monkeypatch.setattr(pilot.sys,'argv',['pilot']+BASE+['--verification-context-policy','preceding-children-v1'])
    monkeypatch.setattr(Path,'read_bytes',lambda *args,**kwargs:pytest.fail('Cache read before validation'))
    with pytest.raises(SystemExit) as stopped:pilot.main()
    assert stopped.value.code==2
    assert 'Invalid verification protocol/context combination' in capsys.readouterr().err
