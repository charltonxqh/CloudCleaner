"""Conditional edges for the LangGraph workflow.

Order of the two gates between ASSESS and EXECUTE:

  plan          works out WHAT steps a retirement takes and in WHICH ORDER
                (read-only; AWS refuses dependent deletes one blocker at a time)
  policy_check  decides WHETHER the proposed action is permitted (risk-scored)

Planning first means the policy gate — and the human it may summon — sees the
full ordered sequence rather than a bare "stop this instance".
"""

from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import PolicyDecision

ACTIONABLE = ("stop", "retire")


def after_detect(state: CloudCleanerState) -> str:
    return "end" if state.get("done_reason") else "investigate"


def after_assess(state: CloudCleanerState) -> str:
    if state.get("force_plan"):
        return "plan"

    rec = state.get("recommendation")
    if rec is None or rec.action not in ACTIONABLE:
        return "record"
    return "plan"


def after_plan(state: CloudCleanerState) -> str:
    plan = state.get("plan")
    if plan is None or plan.blocked or not plan.steps:
        return "record"
    return "policy_check"


def route_after_policy_check(state) -> str:
    """Only bother a human when the policy engine actually says so. ALLOW,
    BLOCK, and "nothing was proposed" all skip straight to execute, which
    already knows how to handle each of those cases correctly.

    Exception: a teardown containing irreversible steps always goes to a
    human, whatever the risk score said. Terminating an instance or deleting
    a volume cannot be undone by the rollback node.
    """
    plan = state.get("plan")
    if plan is not None and plan.irreversible_steps:
        return "approval"

    policy_result = state.get("policy_result")
    if policy_result is not None and policy_result.decision == PolicyDecision.NEEDS_APPROVAL:
        return "approval"
    return "execute"


def route_after_approval(state) -> str:
    """Loop back into the approval node until enough rounds have been
    collected (see policy/safety.py's required_approvals - currently always
    1, but this supports more if a future rule ever needs it).
    """
    approval = state.get("approval")
    if approval is not None and approval.decision != "approve":
        # A human declined. Record the run rather than executing anyway.
        return "record"

    policy_result = state.get("policy_result")
    required = policy_result.required_approvals if policy_result else 1
    rounds = state.get("approval_rounds", 0)
    if rounds < required:
        return "approval"
    return "execute"


def route_after_verify(state) -> str:
    verifications = state.get("verification_results") or []
    if not verifications:
        # Nothing was executed via the single-Action path (blocked, not
        # approved, or a teardown plan ran instead) - nothing to roll back.
        return "complete"
    return "complete" if verifications[-1].verified else "rollback"
