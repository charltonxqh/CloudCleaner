import boto3
import pytest
from moto import mock_aws

from cloudcleaner.graph.nodes.verify import verify_action
from cloudcleaner.tools.aws.actions import propose_start_instance, propose_stop_instance


@pytest.fixture
def ec2_instance():
    with mock_aws():
        client = boto3.client("ec2", region_name="us-east-1")
        resp = client.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")
        yield client, resp["Instances"][0]["InstanceId"]


def test_verify_succeeds_when_state_matches_expected(ec2_instance):
    client, instance_id = ec2_instance
    client.stop_instances(InstanceIds=[instance_id])
    client.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

    action = propose_stop_instance(instance_id, "us-east-1", "idle")
    result = verify_action(action, max_attempts=3, delay_seconds=0)
    assert result.verified is True
    assert result.expected_state == "stopped"
    assert result.attempts == 1


def test_verify_fails_after_max_attempts_when_state_never_matches(ec2_instance):
    client, instance_id = ec2_instance
    # Leave the instance running while claiming a stop action, so the
    # expected state ("stopped") never matches.
    action = propose_stop_instance(instance_id, "us-east-1", "idle")
    result = verify_action(action, max_attempts=3, delay_seconds=0)
    assert result.verified is False
    assert result.attempts == 3
    assert result.actual_state == "running"


def test_verify_start_action_expects_running_state(ec2_instance):
    client, instance_id = ec2_instance
    action = propose_start_instance(instance_id, "us-east-1", "restart")
    result = verify_action(action, max_attempts=3, delay_seconds=0)
    assert result.verified is True
    assert result.expected_state == "running"


def test_verify_handles_nonexistent_instance_without_crashing():
    with mock_aws():
        action = propose_stop_instance("i-doesnotexist12345", "us-east-1", "idle")
        result = verify_action(action, max_attempts=3, delay_seconds=0)
    assert result.verified is False
    assert "lookup failed" in result.actual_state
