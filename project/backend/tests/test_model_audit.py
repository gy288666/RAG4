"""Model treatment changes one setting and rejects incompatible controls."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.research.model import CompletionSpec
from scripts.evaluate_claim_audit import cases_for, model_treatment, treatment_spec

BACKEND = Path(__file__).resolve().parents[1]


def test_model_override_keeps_every_other_completion_setting_frozen():
    source = CompletionSpec(endpoint='https://example.test/v1/chat/completions', model_id='small',
                            verification_protocol='facet-handles-v5', verification_context_policy='preceding-children-v1',
                            timeout_seconds=41, max_output_tokens=2048, response_format='json_object')
    treatment = treatment_spec(source, 'research-operator-v1', 'larger')
    assert treatment.model_dump(exclude={'model_id'}) == source.model_dump(exclude={'model_id'})
    assert treatment.model_id == 'larger' and source.model_id == 'small'


@pytest.fixture
def control(tmp_path):
    record = json.loads((BACKEND/'evaluation/results/research_claim_audit_20261101.json').read_text(encoding='utf-8'))
    source = json.loads((BACKEND/'evaluation/results/research_context_e2e_20261101.json').read_text(encoding='utf-8'))
    # An isolated source manifest exercises the integrity guard without pinning
    # future unrelated production edits to this historical experiment's bytes.
    dependency = tmp_path/'app/research/model.py'
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes(b'# Frozen unit control dependency\n')
    old = record['live_report']
    old['code_sha256'] = {'app/research/model.py': hashlib.sha256(dependency.read_bytes()).hexdigest()}
    return old, {'claims': source['claims'], 'completion': source['original_run']['completion_spec']}, tmp_path


def test_four_real_frozen_single_claim_controls_are_reused_without_network(control):
    old, source, backend = control
    before = copy.deepcopy(old)
    scores = model_treatment('larger', {'candidates': ['larger']}, old, source, cases_for(source), backend)
    assert len(scores) == 4
    assert sum(s['score']['semantic_matched'] for s in scores) == 1
    assert old == before


@pytest.mark.parametrize('mutation', ['not_listed', 'same_model', 'case', 'inventory', 'hash', 'missing_run', 'failed', 'prompt', 'model'])
def test_treatment_rejects_invalid_catalog_or_control_before_credentials(control, mutation):
    old, source, backend = copy.deepcopy(control)
    catalog = {'candidates': ['larger']}
    chosen = 'larger'
    if mutation == 'not_listed': catalog['candidates'] = []
    elif mutation == 'same_model':
        chosen = source['completion']['model_id']; catalog['candidates'] = [chosen]
    elif mutation == 'case': old['cases'][0]['claim']['statement'] = 'changed'
    elif mutation == 'inventory': del old['code_sha256']['app/research/model.py']
    elif mutation == 'hash': old['code_sha256']['app/research/model.py'] = '0'*64
    elif mutation == 'missing_run': old['runs'] = old['runs'][1:]
    elif mutation == 'failed': old['runs'][0]['status'] = 'failed'
    elif mutation == 'prompt': old['calls'][0]['prompt_sha256'] = '0'*64
    else: old['calls'][0]['model_id'] = 'foreign'
    with pytest.raises(ValueError):
        model_treatment(chosen, catalog, old, source, cases_for(source), backend)
