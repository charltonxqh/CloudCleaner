from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import ExecutionStatus, ResourceContext
from cloudcleaner.tools.aws.actions import (
    execute_start_instance,
    execute_stop_instance,
    get_instance_state,
    propose_start_instance,
    propose_stop_instance,
    stop_ec2_instance,
)


@pytest.fixture(autouse=True)
def _reset_metrics():
    METRICS.reset()
    yield
    METRICS.reset()


@pytest.fixture
def ec2_instance():
    with mock_aws():
        client = boto3.client("ec2", region_name="us-east-1")
        resp = client.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t2.micro",
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Owner", "Value": "amanda"},
                        {"Key": "Environment", "Value": "dev"},
                    ],
                }
            ],
        )
        instance_id = resp["Instances"][0]["InstanceId"]
        yield client, instance_id


def _ctx(instance_id, **overrides) -> ResourceContext:
    defaults = dict(
        resource_id=instance_id,
        region="us-east-1",
        tags={"Environment": "dev", "Owner": "amanda"},
        state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    defaults.update(overrides)
    return ResourceContext(**defaults)


def test_stop_instance_happy_path(ec2_instance, monkeypatch):
    monkeypatch.setattr("cloudcleaner.config.settings.DRY_RUN", False)
    client, instance_id = ec2_instance
    action = propose_stop_instance(instance_id, "us-east-1", "idle")
    result = execute_stop_instance(action)
    assert result.status == ExecutionStatus.EXECUTED
    assert result.previous_state == "running"
    assert get_instance_state("us-east-1", instance_id) in ("stopping", "stopped")


def test_stop_instance_idempotent_when_already_stopped(ec2_instance, monkeypatch):
    monkeypatch.setattr("cloudcleaner.config.settings.DRY_RUN", False)
    client, instance_id = ec2_instance
    client.stop_instances(InstanceIds=[instance_id])
    client.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

    action = propose_stop_instance(instance_id, "us-east-1", "idle")
    result = execute_stop_instance(action)
    assert result.idempotent_noop is True
    assert result.status == ExecutionStatus.EXECUTED


def test_start_instance_happy_path(ec2_instance, monkeypatch):
    monkeypatch.setattr("cloudcleaner.config.settings.DRY_RUN", False)
    client, instance_id = ec2_instance
    client.stop_instances(InstanceIds=[instance_id])
    client.get_waiter("instance_stopped").wait(InstanceIds=[instance_id])

    action = propose_start_instance(instance_id, "us-east-1", "restart")
    result = execute_start_instance(action)
    assert result.status == ExecutionStatus.EXECUTED
    assert result.previous_state == "stopped"


def test_dry_run_does_not_mutate_aws_state(ec2_instance, monkeypatch):
    monkeypatch.setattr("cloudcleaner.config.settings.DRY_RUN", True)
    client, instance_id = ec2_instance
    action = propose_stop_instance(instance_id, "us-east-1", "idle")
    assert action.dry_run is True

    result = execute_stop_instance(action)
    assert result.status == ExecutionStatus.SKIPPED_DRY_RUN
    assert get_instance_state("us-east-1", instance_id) == "running"


def test_stop_ec2_instance_tool_blocked_by_policy_for_prod_tag(ec2_instance):
    client, instance_id = ec2_instance
    client.create_tags(Resources=[instance_id], Tags=[{"Key": "Environment", "Value": "prod"}])
    ctx = _ctx(instance_id, tags={"Environment": "prod", "Owner": "amanda"})

    class FakeRuntime:
        state = {"resource_context": ctx}
        tool_call_id = "call-1"

    command = stop_ec2_instance.func(
        instance_id=instance_id, region="us-east-1", reason="idle", runtime=FakeRuntime()
    )
    execution_result = command.update["execution_results"][0]
    assert execution_result.status == ExecutionStatus.BLOCKED
    assert get_instance_state("us-east-1", instance_id) == "running"


def test_get_instance_state_handles_missing_instance():
    with mock_aws():
        with pytest.raises(Exception):
            get_instance_state("us-east-1", "i-doesnotexist")
