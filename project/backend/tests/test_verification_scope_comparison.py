"""Diagnostic counters must expose both rejection and acceptance errors."""
from scripts.compare_verification_scope import POLICIES, summary


def test_rejecting_every_claim_does_not_pass_balanced_diagnostic():
    rows = [dict(policy=p, expected_status=expected, verdict={'status':'insufficient'})
            for p in POLICIES for expected in ('supported', 'insufficient')]
    for result in summary(rows).values():
        assert result == {'completed':2, 'exact_status_matches':1,
                          'false_accepts_against_agent_draft':0,
                          'false_rejects_against_agent_draft':1}


def test_failed_requests_are_not_counted_as_successful_rejections():
    rows = [dict(policy=POLICIES[0], expected_status='insufficient', error_type='TimeoutError'),
            dict(policy=POLICIES[0], expected_status='insufficient', verdict={'status':'supported'})]
    result = summary(rows)
    assert result[POLICIES[0]]['completed'] == 1
    assert result[POLICIES[0]]['false_accepts_against_agent_draft'] == 1
    assert result[POLICIES[1]]['completed'] == 0
