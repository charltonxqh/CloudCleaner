import boto3
import pytest
from moto import mock_aws

from cloudcleaner.graph.nodes.rollback import rollback_action
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import ActionType, VerificationResult
from cloudcleaner.tools.aws.actions import propose_start_instance, propose_stop_instance


@pytest.fixture(autouse=True)
def _fast_verify_and_reset_metrics(monkeypatch):
    monkeypatch.setattr("cloudcleaner.config.settings.VERIFY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr("cloudcleaner.config.settings.VERIFY_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("cloudcleaner.config.settings.ROLLBACK_MAX_RETRIES", 2)
    monkeypatch.setattr("cloudcleaner.config.settings.DRY_RUN", False)
    METRICS.reset()
    yield
    METRICS.reset()


@pytest.fixture
def ec2_instance():
    with mock_aws():
        client = boto3.client("ec2", region_name="us-east-1")
        resp = client.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")
        yield client, resp["Instances"][0]["InstanceId"]


def test_rollback_restarts_instance_after_failed_stop_verification(ec2_instance):
    client, instance_id = ec2_instance
    # Simulate: a stop was attempted but the instance is still running.
    stop_action = propose_stop_instance(instance_id, "us-east-1", "idle")
    failed_verification = VerificationResult(
        action_id=stop_action.id, expected_state="stopped", actual_state="running",
        verified=False, attempts=1,
    )

    result = rollback_action(stop_action, failed_verification)

    assert result.escalated is False
    assert result.rollback_action.action_type == ActionType.START_INSTANCE
    assert result.rollback_verification.verified is True
    assert METRICS.summary().get("rolled_back") == 1


def test_rollback_escalates_when_start_retries_exhausted(ec2_instance, monkeypatch):
    client, instance_id = ec2_instance
    # Force every post-retry check to report "stopped" regardless of what
    # moto actually does, so the retry loop is guaranteed to exhaust.
    monkeypatch.setattr(
        "cloudcleaner.graph.nodes.verify.get_instance_state", lambda region, iid: "stopped"
    )

    start_action = propose_start_instance(instance_id, "us-east-1", "bring back up")
    failed_verification = VerificationResult(
        action_id=start_action.id, expected_state="running", actual_state="unknown",
        verified=False, attempts=1,
    )

    result = rollback_action(start_action, failed_verification)

    assert result.escalated is True
    assert METRICS.summary().get("rollback_escalated") == 1


def test_metrics_count_rolled_back_and_escalated(ec2_instance):
    client, instance_id = ec2_instance
    stop_action = propose_stop_instance(instance_id, "us-east-1", "idle")
    failed_verification = VerificationResult(
        action_id=stop_action.id, expected_state="stopped", actual_state="running",
        verified=False, attempts=1,
    )
    rollback_action(stop_action, failed_verification)
    assert METRICS.summary() == {"rolled_back": 1}
