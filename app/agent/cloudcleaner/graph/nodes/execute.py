"""EXECUTE node. Kept thin: re-validates safety immediately before touching
AWS (defense-in-depth against tags/state drifting between ASSESS/approval
and now), then delegates to tools/aws/actions.py.
"""

from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.policy.risk import assess_risk
from cloudcleaner.policy.safety import evaluate_safety
from cloudcleaner.schemas import ExecutionResult, ExecutionStatus, PolicyDecision
from cloudcleaner.tools.aws.actions import execute_action


def execute_node(state: CloudCleanerState) -> dict:
    action = state["pending_action"]
    ctx = state["resource_context"]

    gate = evaluate_safety(action, ctx, assess_risk(action, ctx))
    if gate.decision == PolicyDecision.BLOCK:
        METRICS.record("blocked_at_execute")
        result = ExecutionResult(
            action_id=action.id,
            status=ExecutionStatus.BLOCKED,
            error="re-check failed: " + "; ".join(v.message for v in gate.violations),
        )
    else:
        result = execute_action(action)
        METRICS.record(f"executed_{result.status.value}")

    return {"execution_results": [result]}
