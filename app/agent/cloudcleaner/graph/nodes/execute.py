"""EXECUTE node. Kept thin: re-validates safety immediately before touching
AWS (defense-in-depth against tags/state drifting between the earlier
policy_check/approval steps and now), then delegates to tools/aws/actions.py.

By the time this node runs, policy_check_node + approval_node (see
graph.py's routing) have already decided this is safe to proceed: either
the decision was ALLOW (no human needed), or it was NEEDS_APPROVAL and
enough approval rounds were collected. This node re-derives everything
fresh rather than trusting state["policy_result"] from earlier, in case
anything changed in the meantime.

Only `recommendation.action == "stop"` maps to a real action today (this is
the only destructive action the team scoped for the hackathon). "keep" and
"investigate_more" are no-ops here.
"""

from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy.context import build_resource_context
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.policy.risk import assess_risk
from cloudcleaner.policy.safety import evaluate_safety
from cloudcleaner.schemas import ExecutionResult, ExecutionStatus, PolicyDecision
from cloudcleaner.tools.aws.actions import ACTIONS, execute_action, propose_stop_instance
from cloudcleaner.config import DRY_RUN
from cloudcleaner.evidence.collector import log


def _execute_pending_action(state: CloudCleanerState) -> dict:
    resource = state["resource"]
    recommendation = state["recommendation"]
    approval = state["approval"]

    if recommendation.action != "stop":
        return {"execution_results": [], "verification_results": []}

    ctx = build_resource_context(resource, state.get("aws_evidence"), state.get("github_evidence"))
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


def _execute_plan(state: CloudCleanerState, plan) -> dict:
    """Run an ordered teardown. Stops at the first failure rather than
    continuing down a sequence whose preconditions no longer hold.
    """
    approved = set(state["approval"].approved_resource_ids or [])
    results, snapshots = [], {}

    if plan.root_resource_id not in approved:
        log.emit("execute", "skip", plan.root_resource_id, "root resource not approved")
        return {"action_results": []}

    for step in plan.steps:
        fn = ACTIONS.get(step.action)
        if fn is None:
            log.emit("execute", "error", step.resource_id, f"unknown action {step.action}")
            continue

        try:
            result = fn(step.resource_id, dry_run=DRY_RUN)
        except Exception as e:
            log.emit("execute", "error", step.resource_id, f"{step.action} failed: {e}")
            results.append({"action": step.action, "resource_id": step.resource_id,
                            "ok": False, "detail": str(e), "dry_run": DRY_RUN})
            break

        if step.action == "snapshot_volume" and not DRY_RUN:
            snapshots[step.resource_id] = result["detail"]

        log.emit("execute", "action", step.resource_id,
                 f"{step.order}. {step.action} -> {result['detail']}", dry_run=result["dry_run"])
        results.append(dict(result))

    if plan.restore and snapshots:
        plan.restore.volume_snapshots = snapshots

    return {"action_results": results}


def execute_node(state: CloudCleanerState) -> dict:
    """Two execution paths share this node.

    A TeardownPlan means a multi-step retirement was planned, so the plan wins.
    Without one we fall back to the single-Action path, which is what the
    policy gate proposed and what the Safety/Actions tests exercise.
    """
    plan = state.get("plan")
    if plan is not None and plan.steps:
        return _execute_plan(state, plan)
    return _execute_pending_action(state)
