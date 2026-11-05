"""The opt-in gate must survive verifier, checkpoint and composer seams."""
import json
from pathlib import Path

import pytest

from app.research.artifacts import ArtifactComposer, ComparisonArtifact, EvidenceVerifier, VerificationReport
from app.research.model import CompletionSpec
from test_result_conditions import example
from test_verification_facets import FacetModel


def model(policy='explicit-row-v1'):
    judge=FacetModel()
    judge.result_condition_policy=policy
    return judge


def test_overconfident_judge_cannot_bypass_actual_cc_news_omission():
    corpus,claim=example()
    judge=model()
    report=EvidenceVerifier(judge).verify(corpus,(claim,))
    assert report.supported==0 and judge.payload is None
    assert report.condition_audits[0].status=='missing'
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'REALM'},(claim,),report)
    assert not artifact.citations and artifact.rows[0].cells[2].status=='uncertain'
    saved=ComparisonArtifact.model_validate_json(artifact.model_dump_json())
    assert saved==artifact and saved.artifact_id==saved.expected_id()


def test_complete_condition_still_requires_model_and_roundtrips():
    corpus,claim=example('CC-News: REALM EM 38.5, Recall@5 52.0.')
    judge=model()
    report=EvidenceVerifier(judge).verify(corpus,(claim,))
    assert judge.payload is not None and report.supported==1
    assert report.condition_audits[0].status=='passed'
    assert VerificationReport.model_validate_json(report.model_dump_json())==report
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'REALM'},(claim,),report)
    assert artifact.citations==(claim,)


@pytest.mark.parametrize('mutation',['missing_audit','forged_status','duplicate','foreign_claim','changed_row'])
def test_composer_rebuilds_audits_instead_of_trusting_status(mutation):
    corpus,claim=example()
    report=EvidenceVerifier(model()).verify(corpus,(claim,))
    audit=report.condition_audits[0]
    forged=report.model_copy(update={'supported':1,'verdicts':(report.verdicts[0].model_copy(update={'status':'supported'}),)})
    if mutation=='missing_audit':audits=()
    elif mutation=='forged_status':audits=(audit.model_copy(update={'status':'passed'}),)
    elif mutation=='duplicate':audits=(audit,audit)
    elif mutation=='foreign_claim':audits=(audit.model_copy(update={'claim_id':'foreign'}),)
    else:audits=(audit.model_copy(update={'row':audit.row.model_copy(update={'label':claim.citation})}),)
    with pytest.raises(ValueError):
        ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'REALM'},(claim,),forged.model_copy(update={'condition_audits':audits}))


def test_historical_report_and_completion_dump_stay_identical():
    corpus,claim=example()
    report=EvidenceVerifier(model('model-only-v1')).verify(corpus,(claim,))
    assert report.supported==1 and not report.condition_audits
    assert 'result_condition_policy' not in json.loads(report.model_dump_json())
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test')
    assert 'result_condition_policy' not in spec.model_dump()
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'REALM'},(claim,),report)
    assert ComparisonArtifact.model_validate_json(artifact.model_dump_json()).artifact_id==artifact.artifact_id


def test_unknown_layout_is_not_passed_by_model_approval():
    corpus,claim=example('EM 38.5 and 52.0.','The model achieves 38.5 and 52.0 in prose.')
    judge=model()
    report=EvidenceVerifier(judge).verify(corpus,(claim,))
    assert report.supported==0 and judge.payload is None
    assert report.condition_audits[0].status=='unknown'


def test_cli_policy_is_opt_in():
    from scripts.evaluate_research_comparison import parse_options,completion_for
    args=['--pilot','pilot','--sources','sources','--cached-run','cache','--cached-report-sha256','0'*64,'--output','new']
    assert completion_for(parse_options(args)).result_condition_policy=='model-only-v1'
    assert completion_for(parse_options(args+['--result-condition-policy','explicit-row-v1'])).result_condition_policy=='explicit-row-v1'


def test_actual_historical_artifact_keeps_its_identity():
    raw=json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/research_context_e2e_20261101.json').read_text(encoding='utf-8'))
    artifact=ComparisonArtifact.model_validate(raw['artifact'])
    assert artifact.artifact_id==artifact.expected_id()
    assert artifact.model_dump(mode='json')==raw['artifact']
    assert CompletionSpec.model_validate(raw['original_run']['completion_spec']).model_dump(mode='json')==raw['original_run']['completion_spec']
