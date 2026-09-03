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
    if policy_result.decision == PolicyDecision.BLOCK:
        result = _blocked_result(action, [v.message for v in policy_result.violations])
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
    if policy_result.decision == PolicyDecision.BLOCK:
        result = _blocked_result(action, [v.message for v in policy_result.violations])
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
