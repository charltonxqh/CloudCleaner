"""EC2 stop/start actions. Destructive calls live only in this file, kept
separate from read-only investigation tools (tools/aws/inventory.py etc).
"""

import boto3
from botocore.exceptions import ClientError
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

from cloudcleaner.config import settings
from cloudcleaner.policy import evaluate_action
from cloudcleaner.schemas import (
    Action,
    ActionType,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    ResourceContext,
)

_ENTERING_STATE = {"stopped": "stopping", "running": "pending"}


def _ec2_client(region: str):
    return boto3.client("ec2", region_name=region)


def get_instance_state(region: str, instance_id: str) -> str:
    """Public - reused by graph/nodes/verify.py."""
    client = _ec2_client(region)
    resp = client.describe_instances(InstanceIds=[instance_id])
    return resp["Reservations"][0]["Instances"][0]["State"]["Name"]


# --- propose: pure, no AWS calls, no side effects ---


def propose_stop_instance(
    instance_id: str, region: str, reason: str, requested_by: str = "cloudcleaner-agent"
) -> Action:
    return Action(
        action_type=ActionType.STOP_INSTANCE,
        resource_id=instance_id,
        region=region,
        reason=reason,
        requested_by=requested_by,
        dry_run=settings.DRY_RUN,
    )


def propose_start_instance(
    instance_id: str, region: str, reason: str, requested_by: str = "cloudcleaner-agent"
) -> Action:
    return Action(
        action_type=ActionType.START_INSTANCE,
        resource_id=instance_id,
        region=region,
        reason=reason,
        requested_by=requested_by,
        dry_run=settings.DRY_RUN,
    )


# --- execute: real (or dry-run) AWS mutation, idempotent, error-handled ---


def _execute(action: Action, target_state: str, api_call) -> ExecutionResult:
    try:
        current = get_instance_state(action.region, action.resource_id)
    except ClientError as e:
        return ExecutionResult(action_id=action.id, status=ExecutionStatus.FAILED, error=str(e))

    if current == target_state or current == _ENTERING_STATE.get(target_state):
        return ExecutionResult(
            action_id=action.id,
            status=ExecutionStatus.EXECUTED,
            previous_state=current,
            new_state=current,
            idempotent_noop=True,
            dry_run=action.dry_run,
        )

    if action.dry_run:
        return ExecutionResult(
            action_id=action.id,
            status=ExecutionStatus.SKIPPED_DRY_RUN,
            previous_state=current,
            new_state=f"{target_state} (simulated)",
            dry_run=True,
        )

    try:
        api_call()
    except ClientError as e:
        return ExecutionResult(
            action_id=action.id, status=ExecutionStatus.FAILED, previous_state=current, error=str(e)
        )

    return ExecutionResult(
        action_id=action.id,
        status=ExecutionStatus.EXECUTED,
        previous_state=current,
        new_state=_ENTERING_STATE[target_state],
        dry_run=False,
    )


def execute_stop_instance(action: Action) -> ExecutionResult:
    client = _ec2_client(action.region)
    return _execute(
        action, "stopped", lambda: client.stop_instances(InstanceIds=[action.resource_id])
    )


def execute_start_instance(action: Action) -> ExecutionResult:
    client = _ec2_client(action.region)
    return _execute(
        action, "running", lambda: client.start_instances(InstanceIds=[action.resource_id])
    )


_EXECUTORS = {
    ActionType.STOP_INSTANCE: execute_stop_instance,
    ActionType.START_INSTANCE: execute_start_instance,
}


def execute_action(action: Action) -> ExecutionResult:
    return _EXECUTORS[action.action_type](action)


# --- LLM-facing tools: propose + gate + execute, mutate graph state ---


def _blocked_result(action: Action, violation_messages: list[str]) -> ExecutionResult:
    return ExecutionResult(
        action_id=action.id, status=ExecutionStatus.BLOCKED, error="; ".join(violation_messages)
    )


@tool
def stop_ec2_instance(instance_id: str, region: str, reason: str, runtime: ToolRuntime) -> Command:
    """Stop an EC2 instance after policy evaluation. Blocked actions are
    reported but not executed.
    """
    ctx: ResourceContext = runtime.state["resource_context"]
    action = propose_stop_instance(instance_id, region, reason)
    policy_result = evaluate_action(action, ctx)
    if policy_result.decision != PolicyDecision.ALLOW:
        # BLOCK or NEEDS_APPROVAL both mean "don't execute directly here" -
        # a tool call has no human-in-the-loop step of its own, so anything
        # short of a clean ALLOW must not proceed without going through the
        # graph's approval flow instead.
        result = _blocked_result(action, [v.message for v in policy_result.violations] or
                                  [f"policy decision was '{policy_result.decision.value}', not 'allow'"])
    else:
        result = execute_stop_instance(action)
    return Command(
        update={
            "pending_action": action,
            "policy_result": policy_result,
            "execution_results": [result],
        }
    )


@tool
def start_ec2_instance(instance_id: str, region: str, reason: str, runtime: ToolRuntime) -> Command:
    """Start an EC2 instance after policy evaluation. Blocked actions are
    reported but not executed.
    """
    ctx: ResourceContext = runtime.state["resource_context"]
    action = propose_start_instance(instance_id, region, reason)
    policy_result = evaluate_action(action, ctx)
    if policy_result.decision != PolicyDecision.ALLOW:
        result = _blocked_result(action, [v.message for v in policy_result.violations] or
                                  [f"policy decision was '{policy_result.decision.value}', not 'allow'"])
    else:
        result = execute_start_instance(action)
    return Command(
        update={
            "pending_action": action,
            "policy_result": policy_result,
            "execution_results": [result],
        }
    )


action_tools = [stop_ec2_instance, start_ec2_instance]


# --- Teardown actions ---
# Owned by: policy/dependencies.py, graph/nodes/{plan,execute}.py
#
# A retirement touches more than the instance: volumes AWS will not clean up,
# public IPv4 addresses, snapshots. These take a plain resource id and default
# to dry_run so a caller has to opt in to touching the account.


class ActionResult(dict):
    pass


def _result(action: str, resource_id: str, ok: bool, detail: str = "", dry_run: bool = False):
    return ActionResult(
        action=action, resource_id=resource_id, ok=ok, detail=detail, dry_run=dry_run
    )


def stop_instance(instance_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("stop_instance", instance_id, True, "dry run", True)
    resp = _ec2_client(settings.AWS_REGION).stop_instances(InstanceIds=[instance_id])
    return _result("stop_instance", instance_id, True,
                   resp["StoppingInstances"][0]["CurrentState"]["Name"])


def terminate_instance(instance_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("terminate_instance", instance_id, True, "dry run", True)
    resp = _ec2_client(settings.AWS_REGION).terminate_instances(InstanceIds=[instance_id])
    return _result("terminate_instance", instance_id, True,
                   resp["TerminatingInstances"][0]["CurrentState"]["Name"])


def snapshot_volume(volume_id: str, description: str = "", dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("snapshot_volume", volume_id, True, "dry run", True)
    resp = _ec2_client(settings.AWS_REGION).create_snapshot(
        VolumeId=volume_id,
        Description=description or f"cloudcleaner restore point for {volume_id}",
        TagSpecifications=[{
            "ResourceType": "snapshot",
            "Tags": [{"Key": "CreatedBy", "Value": "cloudcleaner"}],
        }],
    )
    return _result("snapshot_volume", volume_id, True, resp["SnapshotId"])


def delete_volume(volume_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("delete_volume", volume_id, True, "dry run", True)
    _ec2_client(settings.AWS_REGION).delete_volume(VolumeId=volume_id)
    return _result("delete_volume", volume_id, True, "deleted")


def disassociate_address(association_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("disassociate_address", association_id, True, "dry run", True)
    _ec2_client(settings.AWS_REGION).disassociate_address(AssociationId=association_id)
    return _result("disassociate_address", association_id, True, "disassociated")


def release_address(allocation_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("release_address", allocation_id, True, "dry run", True)
    _ec2_client(settings.AWS_REGION).release_address(AllocationId=allocation_id)
    return _result("release_address", allocation_id, True, "released")


def delete_snapshot(snapshot_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("delete_snapshot", snapshot_id, True, "dry run", True)
    _ec2_client(settings.AWS_REGION).delete_snapshot(SnapshotId=snapshot_id)
    return _result("delete_snapshot", snapshot_id, True, "deleted")


ACTIONS = {
    "stop_instance": stop_instance,
    "terminate_instance": terminate_instance,
    "snapshot_volume": snapshot_volume,
    "delete_volume": delete_volume,
    "disassociate_address": disassociate_address,
    "release_address": release_address,
    "delete_snapshot": delete_snapshot,
}
