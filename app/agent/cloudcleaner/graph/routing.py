"""Conditional edges for the LangGraph workflow."""

from cloudcleaner.schemas import PolicyDecision


def route_after_policy_check(state) -> str:
    """Only bother a human when the policy engine actually says so. ALLOW,
    BLOCK, and "nothing was proposed" all skip straight to execute, which
    already knows how to handle each of those cases correctly.
    """
    policy_result = state.get("policy_result")
    if policy_result is not None and policy_result.decision == PolicyDecision.NEEDS_APPROVAL:
        return "approval"
    return "execute"


def route_after_approval(state) -> str:
    """Loop back into the approval node until enough rounds have been
    collected (see policy/safety.py's required_approvals - currently always
    1, but this supports more if a future rule ever needs it).
    """
    policy_result = state.get("policy_result")
    required = policy_result.required_approvals if policy_result else 1
    rounds = state.get("approval_rounds", 0)
    if rounds < required:
        return "approval"
    return "execute"


def route_after_verify(state) -> str:
    verifications = state.get("verification_results") or []
    if not verifications:
        # Nothing was executed (blocked, not approved, or recommendation
        # wasn't "stop") - nothing to verify or roll back.
        return "complete"
    return "complete" if verifications[-1].verified else "rollback"
