import pytest

from cloudcleaner.graph.routing import route_after_approval, route_after_policy_check, route_after_verify
from cloudcleaner.schemas import (
    ApprovalDecision,
    PolicyDecision,
    PolicyResult,
    RiskAssessment,
    RiskLevel,
    VerificationResult,
)


def _policy_result(decision, required_approvals=0) -> PolicyResult:
    return PolicyResult(
        action_id="a1",
        decision=decision,
        risk_assessment=RiskAssessment(action_id="a1", risk_score=0, risk_level=RiskLevel.LOW),
        required_approvals=required_approvals,
    )


def test_route_after_policy_check_goes_to_approval_when_needs_approval():
    state = {"policy_result": _policy_result(PolicyDecision.NEEDS_APPROVAL, required_approvals=1)}
    assert route_after_policy_check(state) == "approval"


@pytest.mark.parametrize("decision", [PolicyDecision.ALLOW, PolicyDecision.BLOCK])
def test_route_after_policy_check_skips_approval_when_not_needed(decision):
    state = {"policy_result": _policy_result(decision)}
    assert route_after_policy_check(state) == "execute"


def test_route_after_policy_check_skips_approval_when_no_policy_result():
    # recommendation wasn't "stop" - policy_check_node never ran evaluation
    assert route_after_policy_check({}) == "execute"


def test_route_after_approval_loops_when_rounds_insufficient():
    state = {
        "policy_result": _policy_result(PolicyDecision.NEEDS_APPROVAL, required_approvals=2),
        "approval_rounds": 1,
    }
    assert route_after_approval(state) == "approval"


def test_route_after_approval_proceeds_when_rounds_sufficient():
    state = {
        "policy_result": _policy_result(PolicyDecision.NEEDS_APPROVAL, required_approvals=2),
        "approval_rounds": 2,
    }
    assert route_after_approval(state) == "execute"


def test_route_after_approval_single_round_case():
    state = {
        "policy_result": _policy_result(PolicyDecision.NEEDS_APPROVAL, required_approvals=1),
        "approval_rounds": 1,
    }
    assert route_after_approval(state) == "execute"


def test_route_after_approval_defaults_to_one_round_when_no_policy_result():
    assert route_after_approval({"approval_rounds": 1}) == "execute"
    assert route_after_approval({"approval_rounds": 0}) == "approval"


def _verification(verified: bool) -> VerificationResult:
    return VerificationResult(
        action_id="a1", expected_state="stopped", actual_state="stopped" if verified else "running",
        verified=verified, attempts=1,
    )


def test_route_after_verify_complete_when_verified():
    assert route_after_verify({"verification_results": [_verification(True)]}) == "complete"


def test_route_after_verify_rollback_when_not_verified():
    assert route_after_verify({"verification_results": [_verification(False)]}) == "rollback"


def test_route_after_verify_complete_when_nothing_was_executed():
    assert route_after_verify({"verification_results": []}) == "complete"
    assert route_after_verify({}) == "complete"


# --- the non-interactive approval trap ---
# An invalid answer deliberately loops back into the approval node so a human
# can retype it. Anything answering on a human's behalf must therefore decline
# explicitly: resuming with "" parses as invalid, and with nobody to re-prompt
# the graph interrupts forever. cli.py hit exactly this.


def test_invalid_approval_loops_back_for_a_retype():
    state = {"approval": ApprovalDecision(decision="invalid", reason="unrecognised")}
    assert route_after_approval(state) == "approval"


def test_an_explicit_rejection_terminates_instead_of_looping():
    state = {"approval": ApprovalDecision(decision="reject", approved_by="cli:non-interactive")}
    assert route_after_approval(state) == "record"


def test_an_empty_answer_is_invalid_not_a_rejection():
    """The distinction the CLI hang turned on."""
    from cloudcleaner.policy.approval import parse_approval

    assert parse_approval("", "i-1")["valid"] is False
