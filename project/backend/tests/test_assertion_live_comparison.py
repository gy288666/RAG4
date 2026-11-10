"""Live diagnostic selection/gates tested without a provider or credentials."""
import pytest
import scripts.compare_verification_scope as comparison
from app.research.assertions import AssertionCoverageVerifier
from app.research.model import CompletionSpec
from test_assertion_coverage import covered,AtomicModel
from test_verification_assertion_comparison import assertion_fixture


def test_coverage_cases_keep_four_request_cap_and_preceding_context(monkeypatch):
    cases=[('fixture',object(),'insufficient')]*4
    monkeypatch.setattr(comparison,'frozen_cases',lambda *args:cases)
    selected,policies=comparison.experiment_cases(None,None,None,experiment='coverage-v1')
    assert selected is cases and policies==('preceding-children-v1',)
    assert len(selected)*len(policies)==4


def test_realm_plan_covers_exact_original_without_rewriting(assertion_fixture):
    task,corpus,results=assertion_fixture
    claim=comparison.assertion_cases(task,corpus,results)[0][1]
    plan=comparison.coverage_plan(corpus,'realm_method_negative',claim)
    assert len(plan.assertions)==2
    assert ''.join(a.text for a in plan.assertions)==claim.statement
    assert plan.assertions[1].text.startswith('通过')
    assert comparison.coverage_expected('realm_method_negative')==('supported','insufficient')
    assert comparison.coverage_expected('realm_method_positive')==('supported','supported')


def test_control_cases_use_explicit_whole_statement_not_automatic_splitting(covered):
    corpus,claim,_=covered
    plan=comparison.coverage_plan(corpus,'fid_attribution_negative',claim)
    assert len(plan.assertions)==1 and plan.assertions[0].text==claim.statement
    assert comparison.coverage_expected('fid_attribution_negative')==('insufficient',)
    with pytest.raises(ValueError):comparison.coverage_plan(corpus,'unknown',claim)
    with pytest.raises(ValueError):comparison.coverage_plan(corpus,'realm_method_negative',claim)


def test_correct_aggregate_cannot_hide_wrong_atomic_judgment(covered):
    corpus,claim,plan=covered
    review,=AssertionCoverageVerifier(AtomicModel(('insufficient','insufficient'))).verify(corpus,(claim,),(plan,))
    row=comparison.coverage_outcome('realm_method_negative',claim,review)
    assert row['verdict']['status']=='insufficient'
    assert row['assertion_expectations_met'] is False
    record={'status':'completed','max_requests':1,'rows':[
        dict(row,case='realm_method_negative',policy='preceding-children-v1',expected_status='insufficient')]}
    assert comparison.diagnostic_exit_code(record)==3


def test_missing_judgment_is_not_counted_as_a_correct_negative(covered):
    corpus,claim,plan=covered;model=AtomicModel();generate=model.generate
    model.generate=lambda op,payload:{'assessments':generate(op,payload)['assessments'][:1]}
    review,=AssertionCoverageVerifier(model).verify(corpus,(claim,),(plan,))
    row=comparison.coverage_outcome('realm_method_negative',claim,review)
    assert row['assertions'][1]['actual_status']=='missing'
    assert not row['assertion_expectations_met']


def test_correct_atomic_judgments_pass_development_gate_only(covered):
    corpus,claim,plan=covered
    review,=AssertionCoverageVerifier(AtomicModel()).verify(corpus,(claim,),(plan,))
    row=comparison.coverage_outcome('realm_method_negative',claim,review)
    assert row['assertion_expectations_met']
    record={'status':'completed','max_requests':1,'rows':[
        dict(row,case='realm_method_negative',policy='preceding-children-v1',expected_status='insufficient')]}
    assert comparison.diagnostic_exit_code(record)==0


def test_single_case_probe_is_explicit_and_preserves_default_matrix():
    cases=[('realm_method_negative',object(),'insufficient'),('fid_attribution_negative',object(),'insufficient')]
    assert comparison.select_coverage_case(cases,'coverage-v1',None) is cases
    assert comparison.select_coverage_case(cases,'coverage-v1','realm_method_negative')==cases[:1]
    with pytest.raises(ValueError):comparison.select_coverage_case(cases,'context-v1','realm_method_negative')
    with pytest.raises(ValueError):comparison.select_coverage_case(cases,'coverage-v1','unknown')


def test_response_format_override_preserves_other_spec_fields():
    spec=CompletionSpec(endpoint='https://example.test/completions',model_id='fixture',
        verification_protocol='facet-handles-v5',verification_context_policy='preceding-children-v1')
    assert comparison.comparison_spec(spec,'preceding-children-v1',None)==spec
    changed=comparison.comparison_spec(spec,'preceding-children-v1','json_object')
    assert changed.model_dump(exclude={'response_format'})==spec.model_dump(exclude={'response_format'})
    assert changed.response_format=='json_object' and spec.response_format=='text'
