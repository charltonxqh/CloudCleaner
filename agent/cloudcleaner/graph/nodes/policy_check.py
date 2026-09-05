"""POLICY_CHECK node. Runs right after ASSESS and before APPROVAL, so the
approval step (and its routing) can actually see the decision and only
bother a human when needed - instead of the old ordering where policy was
only evaluated inside EXECUTE, after approval had already (blindly) run.
"""

from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy import evaluate_action
from cloudcleaner.policy.context import build_resource_context
from cloudcleaner.tools.aws.actions import propose_stop_instance


def policy_check_node(state: CloudCleanerState) -> dict:
    recommendation = state["recommendation"]
    if recommendation.action != "stop":
        # Nothing proposed - nothing for policy to evaluate. execute_node
        # already knows to no-op when there's no pending_action.
        return {}

    resource = state["resource"]
    ctx = build_resource_context(resource, state.get("aws_evidence"), state.get("github_evidence"))
    action = propose_stop_instance(resource.resource_id, resource.region, reason=recommendation.reason)
    policy_result = evaluate_action(action, ctx)

    return {"pending_action": action, "resource_context": ctx, "policy_result": policy_result}
