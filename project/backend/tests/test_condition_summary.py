"""An execution summary cannot double-count checkpoints or imply truth."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.research.artifacts import VerificationReport
from scripts.evaluate_research_comparison import condition_summary


@pytest.fixture
def task():
    record=json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/research_result_conditions_20261101.json').read_text(encoding='utf-8'))['report']
    verification=VerificationReport.model_validate(record['blocked_verification'])
    claim=SimpleNamespace(claim_id=record['blocked_claim']['claim_id'],facet='result')
    return SimpleNamespace(completion=SimpleNamespace(result_condition_policy='explicit-row-v1'),
        claims=(claim,SimpleNamespace(claim_id='pending_result',facet='result')),
        corpus_id=record['blocked_artifact']['corpus_id'],verification=verification,
        verification_batches=(SimpleNamespace(verification=verification),))


def test_merged_report_prevents_double_counting_retained_batches(task):
    result=condition_summary(task)
    assert result['report_source']=='merged' and result['audited_result_count']==1
    assert result['status_counts']=={'passed':0,'missing':1,'unknown':0,'not_applicable':0}
    assert result['blocked_claim_ids']==[task.claims[0].claim_id]
    assert result['unassessed_result_claim_ids']==['pending_result']
    assert result['verification_pending_result_claim_ids']==['pending_result']
    assert result['semantic_quality_inferred'] is False


def test_partial_checkpoints_and_empty_task_are_distinct_from_passes(task):
    task.verification=None
    assert condition_summary(task)['report_source']=='document_checkpoints'
    task.verification_batches=()
    result=condition_summary(task)
    assert result['audited_result_count']==0 and sum(result['status_counts'].values())==0
    assert len(result['verification_pending_result_claim_ids'])==2


def test_old_policy_is_reported_as_disabled_without_implied_condition_pass(task):
    task.completion.result_condition_policy='model-only-v1'
    task.verification=task.verification.model_copy(update={'result_condition_policy':'model-only-v1','condition_audits':()})
    result=condition_summary(task)
    assert result['enabled'] is False
    assert sum(result['status_counts'].values())==0 and result['audited_result_count']==0


def test_duplicate_checkpoint_verdicts_cannot_inflate_coverage(task):
    task.verification=None
    # No audits: exercise the independent verdict duplication fence.
    report=task.verification_batches[0].verification.model_copy(update={'condition_audits':()})
    task.verification_batches=(SimpleNamespace(verification=report),SimpleNamespace(verification=report))
    with pytest.raises(ValueError,match='duplicate verdicts'):condition_summary(task)


@pytest.mark.parametrize('mutation',['policy','foreign_claim','identity','duplicate'])
def test_inconsistent_observation_cannot_be_exported_as_valid(task,mutation):
    report=task.verification
    if mutation=='policy':task.completion.result_condition_policy='model-only-v1'
    elif mutation=='foreign_claim':
        report=report.model_copy(update={'condition_audits':(report.condition_audits[0].model_copy(update={'claim_id':'foreign'}),)})
    elif mutation=='identity':
        report=report.model_copy(update={'condition_audits':(report.condition_audits[0].model_copy(update={'audit_id':'forged'}),)})
    else:report=report.model_copy(update={'condition_audits':report.condition_audits*2})
    task.verification=report
    with pytest.raises(ValueError):condition_summary(task)
