"""Integration-style tests: drive policy_check_node -> approval_node ->
routing together (without the full LangGraph StateGraph, and without a real
LLM for assess_node) to prove the double-approval loop actually terminates
at the right round count for each scenario.
"""

from cloudcleaner.graph.nodes.approval import approval_node
from cloudcleaner.graph.nodes.policy_check import policy_check_node
from cloudcleaner.graph.routing import route_after_approval, route_after_policy_check
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import AWSEvidence, CloudResource, Recommendation
import pytest


@pytest.fixture(autouse=True)
def _reset_metrics():
    METRICS.reset()
    yield
    METRICS.reset()


def _drive_to_execute(resource, aws_evidence, recommendation):
    state = {"resource": resource, "aws_evidence": aws_evidence, "recommendation": recommendation}
    state.update(policy_check_node(state))
    route = route_after_policy_check(state)
    rounds_run = 0
    # Safety net so a routing bug can't hang the test suite.
    for _ in range(10):
        if route != "approval":
            break
        state.update(approval_node(state))
        rounds_run += 1
        route = route_after_approval(state)
    return state, route, rounds_run


def test_prod_stop_requires_exactly_one_approval_round_before_execute():
    # Prod goes through the same single-approval tier as anything else
    # NEEDS_APPROVAL - no special-casing.
    resource = CloudResource(
        resource_id="i-1", resource_type="ec2", region="us-east-1",
        state="running", owner="amanda", environment="prod",
    )
    aws_evidence = AWSEvidence(avg_cpu_percent=1.0, estimated_monthly_cost=20.0)
    recommendation = Recommendation(action="stop", reason="idle", confidence=0.9)

    state, final_route, rounds_run = _drive_to_execute(resource, aws_evidence, recommendation)

    assert rounds_run == 1
    assert state["approval_rounds"] == 1
    assert state["policy_result"].required_approvals == 1
    assert final_route == "execute"


def test_staging_stop_requires_exactly_one_approval_round():
    resource = CloudResource(
        resource_id="i-2", resource_type="ec2", region="us-east-1",
        state="running", owner="amanda", environment="staging",
    )
    # High activity pushes this into NEEDS_APPROVAL territory.
    aws_evidence = AWSEvidence(avg_cpu_percent=50.0, estimated_monthly_cost=20.0)
    recommendation = Recommendation(action="stop", reason="idle", confidence=0.9)

    state, final_route, rounds_run = _drive_to_execute(resource, aws_evidence, recommendation)

    assert rounds_run == 1
    assert final_route == "execute"


def test_low_risk_dev_stop_never_enters_approval_loop():
    resource = CloudResource(
        resource_id="i-3", resource_type="ec2", region="us-east-1",
        state="running", owner="amanda", environment="dev",
    )
    aws_evidence = AWSEvidence(avg_cpu_percent=1.0, estimated_monthly_cost=5.0)
    recommendation = Recommendation(action="stop", reason="idle", confidence=0.9)

    state, final_route, rounds_run = _drive_to_execute(resource, aws_evidence, recommendation)

    assert rounds_run == 0
    assert state["policy_result"].decision.value == "allow"
    assert final_route == "execute"
