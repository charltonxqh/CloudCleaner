"""Deterministic hard-gating safety rules. No LLM, no scoring - pure
boolean/deny logic. Runs at ASSESS time (gates whether human approval is
even offered) and again at EXECUTE time (defense-in-depth re-check in case
tags/state changed between approval and execution).
"""

from collections.abc import Callable
from datetime import datetime, timezone

from cloudcleaner.schemas import (
    Action,
    ActionType,
    PolicyDecision,
    PolicyResult,
    PolicyViolation,
    ResourceContext,
    RiskAssessment,
)

SafetyRule = Callable[[Action, ResourceContext], "PolicyViolation | None"]

PROD_TAG_VALUES = {"prod", "production"}
STOP_COOLDOWN_MINUTES = 15

# Raised from 25 - at 25, too many single-medium-signal resources (e.g. just
# "staging" alone) were tripping NEEDS_APPROVAL. 35 means no single soft
# signal triggers it alone, but prod-level risk (40) and most genuine
# multi-signal combinations still clear it comfortably.
NEEDS_APPROVAL_RISK_THRESHOLD = 35

# Prod doesn't hard-block anymore - it goes through the same single-approval
# flow as any other NEEDS_APPROVAL case. (route_after_approval/approval_rounds
# still support requiring more than one round in general, in case a future
# rule needs it - nothing currently asks for more than 1.)
SINGLE_APPROVAL_REQUIRED = 1


def rule_require_owner_tag(action: Action, ctx: ResourceContext) -> PolicyViolation | None:
    owner = ctx.tags.get("Owner") or ctx.tags.get("owner")
    if not owner and not action.force_override:
        return PolicyViolation(
            rule="require_owner_tag",
            message=f"Instance {ctx.resource_id} has no Owner tag; refusing to act without an owner",
            hard_block=False,
        )
    return None


def rule_block_stop_recently_started(
    action: Action, ctx: ResourceContext
) -> PolicyViolation | None:
    """Cooldown: don't stop something that just changed state (avoids racing
    a rollback that just restarted it, or stopping something a human/other
    process just intentionally brought up).
    """
    if action.action_type != ActionType.STOP_INSTANCE or ctx.last_state_change is None:
        return None
    age_minutes = (datetime.now(timezone.utc) - ctx.last_state_change).total_seconds() / 60
    if age_minutes < STOP_COOLDOWN_MINUTES:
        return PolicyViolation(
            rule="block_stop_recently_started",
            message=(
                f"Instance changed state {age_minutes:.1f}m ago "
                f"(<{STOP_COOLDOWN_MINUTES}m cooldown)"
            ),
            hard_block=True,
        )
    return None


DEFAULT_SAFETY_RULES: list[SafetyRule] = [
    rule_require_owner_tag,
    rule_block_stop_recently_started,
]


def _required_approvals(decision: PolicyDecision) -> int:
    return SINGLE_APPROVAL_REQUIRED if decision == PolicyDecision.NEEDS_APPROVAL else 0


def evaluate_safety(
    action: Action,
    ctx: ResourceContext,
    risk: RiskAssessment,
    rules: list[SafetyRule] | None = None,
) -> PolicyResult:
    violations = [v for rule in (rules or DEFAULT_SAFETY_RULES) if (v := rule(action, ctx))]
    hard_blocks = [v for v in violations if v.hard_block]

    if hard_blocks:
        decision = PolicyDecision.BLOCK
    elif violations or risk.risk_score >= NEEDS_APPROVAL_RISK_THRESHOLD:
        decision = PolicyDecision.NEEDS_APPROVAL
    else:
        decision = PolicyDecision.ALLOW

    return PolicyResult(
        action_id=action.id,
        decision=decision,
        violations=violations,
        risk_assessment=risk,
        required_approvals=_required_approvals(decision),
    )
