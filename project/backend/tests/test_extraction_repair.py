"""Repair admission uses the real failed task and its unchanged original budget."""
import json
from pathlib import Path
import pytest
from app.research.tasks import ResearchTask
from scripts.resume_research_comparison import require_optional_relation_repair


@pytest.fixture
def source():
    r=json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/research_condition_e2e_initial_20261104.json').read_text(encoding='utf-8'))
    return ResearchTask.model_validate(r['task'])


def test_real_checkpoint_can_finish_exactly_with_original_13_steps_8_calls(source):
    step,steps,calls=require_optional_relation_repair(source)
    assert (step,steps,calls)==('analyse-0',8,6)
    assert source.tool_calls_used+steps==source.budget.max_steps==13
    assert source.model_calls_used+calls==source.budget.max_model_calls==8


@pytest.mark.parametrize('mutation',['claim_failure','timeout','steps','calls','search','running'])
def test_other_failures_or_budget_changes_cannot_be_repaired(source,mutation):
    failed=next(s for s in source.steps if s.status=='failed')
    if mutation in {'claim_failure','timeout'}:
        result=failed.result.model_copy(update={'warnings':('response_schema_invalid:extract_cited:claims.0.citation_id:missing',)}
            if mutation=='claim_failure' else {'error_type':'ReadTimeout'})
        source=source.model_copy(update={'steps':tuple(s.model_copy(update={'result':result}) if s.id==failed.id else s for s in source.steps)})
    elif mutation=='steps':source=source.model_copy(update={'budget':source.budget.model_copy(update={'max_steps':12})})
    elif mutation=='calls':source=source.model_copy(update={'budget':source.budget.model_copy(update={'max_model_calls':7})})
    elif mutation=='search':source=source.model_copy(update={'bundles':source.bundles[:-1]})
    else:source=source.model_copy(update={'steps':tuple(s.model_copy(update={'status':'running'}) if s.id=='search-0' else s for s in source.steps)})
    with pytest.raises(ValueError):require_optional_relation_repair(source)
