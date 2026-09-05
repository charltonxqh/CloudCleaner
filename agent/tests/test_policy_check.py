from cloudcleaner.graph.nodes.policy_check import policy_check_node
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import (
    AWSEvidence,
    CloudResource,
    GitHubEvidence,
    PolicyDecision,
    Recommendation,
)
import pytest


@pytest.fixture(autouse=True)
def _reset_metrics():
    METRICS.reset()
    yield
    METRICS.reset()


def _resource(**overrides) -> CloudResource:
    defaults = dict(
        resource_id="i-abc123",
        resource_type="ec2",
        region="us-east-1",
        state="running",
        owner="amanda",
        environment="dev",
    )
    defaults.update(overrides)
    return CloudResource(**defaults)


def _recommendation(action="stop") -> Recommendation:
    return Recommendation(action=action, reason="idle for 30 days", confidence=0.9)


def test_policy_check_evaluates_stop_recommendation():
    state = {
        "resource": _resource(),
        "aws_evidence": AWSEvidence(avg_cpu_percent=1.0, estimated_monthly_cost=20.0),
        "recommendation": _recommendation("stop"),
    }
    result = policy_check_node(state)
    assert result["pending_action"].action_type.value == "stop_instance"
    assert result["resource_context"].resource_id == "i-abc123"
    assert result["policy_result"].decision == PolicyDecision.ALLOW


def test_policy_check_noop_when_recommendation_not_stop():
    state = {"resource": _resource(), "recommendation": _recommendation("keep")}
    assert policy_check_node(state) == {}


def test_policy_check_prod_resource_needs_approval():
    state = {
        "resource": _resource(environment="prod"),
        "aws_evidence": AWSEvidence(avg_cpu_percent=1.0, estimated_monthly_cost=20.0),
        "recommendation": _recommendation("stop"),
    }
    result = policy_check_node(state)
    assert result["policy_result"].decision == PolicyDecision.NEEDS_APPROVAL
    assert result["policy_result"].required_approvals == 1


def test_policy_check_folds_github_evidence_into_context():
    state = {
        "resource": _resource(),
        "aws_evidence": AWSEvidence(avg_cpu_percent=1.0, estimated_monthly_cost=20.0),
        "github_evidence": GitHubEvidence(branch_exists=True, pr_status="open"),
        "recommendation": _recommendation("stop"),
    }
    result = policy_check_node(state)
    assert result["resource_context"].github_pr_open is True
    assert any("GitHub" in reason for reason in result["policy_result"].risk_assessment.reasons)
