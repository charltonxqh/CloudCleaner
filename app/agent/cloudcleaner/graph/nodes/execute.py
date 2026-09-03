"""EXECUTE node. Kept thin: builds the policy inputs from what
DETECT/INVESTIGATE/ASSESS/APPROVAL populated, re-validates safety
immediately before touching AWS (defense-in-depth against tags/state
drifting between ASSESS/approval and now), then delegates to
tools/aws/actions.py.

Only `recommendation.action == "stop"` maps to a real action today (this is
the only destructive action the team scoped for the hackathon). "keep" and
"investigate_more" are no-ops here.
"""

from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.policy.risk import assess_risk
from cloudcleaner.policy.safety import evaluate_safety
from cloudcleaner.schemas import (
    AWSEvidence,
    CloudResource,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    ResourceContext,
)
from cloudcleaner.tools.aws.actions import execute_action, propose_stop_instance

# CPU below this threshold (as a %) counts as "no recent activity" when
# AWSEvidence doesn't give us a direct signal.
ACTIVITY_CPU_THRESHOLD_PERCENT = 5.0


def _resource_context(resource: CloudResource, aws_evidence: AWSEvidence | None) -> ResourceContext:
    tags = dict(resource.tags)
    if resource.owner and "Owner" not in tags:
        tags["Owner"] = resource.owner
    if resource.environment and "Environment" not in tags:
        tags["Environment"] = resource.environment

    recent_activity = None
    cost = None
    if aws_evidence is not None:
        cost = aws_evidence.estimated_monthly_cost
        if aws_evidence.avg_cpu_percent is not None:
            recent_activity = aws_evidence.avg_cpu_percent > ACTIVITY_CPU_THRESHOLD_PERCENT

    return ResourceContext(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        region=resource.region,
        tags=tags,
        state=resource.state or "unknown",
        estimated_monthly_cost_usd=cost,
        recent_activity=recent_activity,
    )


def execute_node(state: CloudCleanerState) -> dict:
    resource = state["resource"]
    recommendation = state["recommendation"]
    approval = state["approval"]

    if recommendation.action != "stop":
        return {"execution_results": [], "verification_results": []}

    ctx = _resource_context(resource, state.get("aws_evidence"))
    action = propose_stop_instance(resource.resource_id, resource.region, reason=recommendation.reason)

    if approval.decision != "approve":
        result = ExecutionResult(
            action_id=action.id,
            status=ExecutionStatus.BLOCKED,
            error=f"human approval decision was '{approval.decision}', not 'approve'",
        )
        METRICS.record("blocked_no_approval")
        return {"pending_action": action, "resource_context": ctx, "execution_results": [result]}

    gate = evaluate_safety(action, ctx, assess_risk(action, ctx))
    if gate.decision == PolicyDecision.BLOCK:
        METRICS.record("blocked_at_execute")
        result = ExecutionResult(
            action_id=action.id,
            status=ExecutionStatus.BLOCKED,
            error="; ".join(v.message for v in gate.violations),
        )
    else:
        result = execute_action(action)
        METRICS.record(f"executed_{result.status.value}")

    return {
        "pending_action": action,
        "resource_context": ctx,
        "policy_result": gate,
        "execution_results": [result],
    }
