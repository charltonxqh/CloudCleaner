"""Demo: policy -> execute -> verify -> rollback, end to end.

    uv run scripts/demo_ec2_lifecycle.py

Runs entirely against a moto-mocked EC2 instance (mock_aws) - safe, fast,
and reproducible for a screen recording. No real AWS account or costs
involved. Each scenario prints its decision trail so the terminal output
alone tells the story; narrate over this for the hackathon video.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `uv run scripts/demo_ec2_lifecycle.py` from app/agent
# without installing cloudcleaner as a package first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3
from moto import mock_aws

from cloudcleaner.config import settings
from cloudcleaner.graph.nodes.approval import approval_node
from cloudcleaner.graph.nodes.rollback import rollback_action
from cloudcleaner.graph.nodes.verify import verify_action
from cloudcleaner.graph.routing import route_after_approval
from cloudcleaner.policy import evaluate_action
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import (
    ExecutionResult,
    PolicyDecision,
    PolicyResult,
    ResourceContext,
    RollbackResult,
    VerificationResult,
)
from cloudcleaner.tools.aws.actions import execute_action, propose_stop_instance


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _print_model(label: str, model) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(json.loads(model.model_dump_json()), indent=2))


def _run_instance(client, tags: dict[str, str]):
    resp = client.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}
        ],
    )
    return resp["Instances"][0]["InstanceId"]


def scenario_happy_path(client) -> None:
    _print_header("SCENARIO 1: happy path - stop an idle, owned dev instance")
    instance_id = _run_instance(client, {"Owner": "amanda", "Environment": "dev"})
    ctx = ResourceContext(
        resource_id=instance_id,
        region="us-east-1",
        tags={"Owner": "amanda", "Environment": "dev"},
        state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=2),
        recent_activity=False,
        estimated_monthly_cost_usd=8.5,
    )
    action = propose_stop_instance(instance_id, "us-east-1", reason="idle >24h, low CPU")
    policy_result: PolicyResult = evaluate_action(action, ctx)
    _print_model("Action proposed", action)
    _print_model("Policy result", policy_result)

    if policy_result.decision == PolicyDecision.BLOCK:
        print("\n-> BLOCKED, not executing.")
        return

    execution: ExecutionResult = execute_action(action)
    _print_model("Execution result", execution)

    verification: VerificationResult = verify_action(action, max_attempts=3, delay_seconds=0)
    _print_model("Verification result", verification)
    print("\n-> COMPLETE." if verification.verified else "\n-> Verification failed, would roll back.")


def scenario_github_evidence_raises_risk(client) -> None:
    _print_header("SCENARIO 2: an open GitHub PR raises risk enough to need approval")
    instance_id = _run_instance(client, {"Owner": "amanda", "Environment": "dev"})
    ctx = ResourceContext(
        resource_id=instance_id,
        region="us-east-1",
        tags={"Owner": "amanda", "Environment": "dev"},
        state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=2),
        recent_activity=None,  # no CloudWatch data yet - treated conservatively
        estimated_monthly_cost_usd=60.0,
        github_pr_open=True,  # the PR that spun this instance up is still open
    )
    action = propose_stop_instance(instance_id, "us-east-1", reason="looked idle, but PR #184 still open")
    policy_result = evaluate_action(action, ctx)
    _print_model("Action proposed", action)
    _print_model("Policy result", policy_result)
    print(
        f"\n-> {policy_result.decision.value.upper()} "
        f"({policy_result.required_approvals} approval(s) required): instance not touched yet."
    )


def scenario_prod_needs_approval(client) -> None:
    _print_header("SCENARIO 3: prod doesn't hard-block anymore - it needs approval like anything else")
    instance_id = _run_instance(client, {"Owner": "amanda", "Environment": "prod"})
    ctx = ResourceContext(
        resource_id=instance_id,
        region="us-east-1",
        tags={"Owner": "amanda", "Environment": "prod"},
        state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    action = propose_stop_instance(instance_id, "us-east-1", reason="flagged as idle (false positive)")
    policy_result = evaluate_action(action, ctx)
    _print_model("Action proposed", action)
    _print_model("Policy result", policy_result)
    print(
        f"\n-> {policy_result.decision.value.upper()}: "
        f"requires {policy_result.required_approvals} human approval(s) before execute runs."
    )

    state = {"policy_result": policy_result, "approval_rounds": 0}
    route = "approval"
    while route == "approval":
        state.update(approval_node(state))
        print(f"   Approval round {state['approval_rounds']}: {state['approval'].reason}")
        route = route_after_approval(state)
    print(f"-> All {policy_result.required_approvals} approval(s) collected, ready for EXECUTE.")

    aws_state = client.describe_instances(InstanceIds=[instance_id])
    state_name = aws_state["Reservations"][0]["Instances"][0]["State"]["Name"]
    print(f"   AWS state so far (execute hasn't run in this scenario): {state_name}")


def scenario_rollback_on_verify_failure(client) -> None:
    _print_header("SCENARIO 4: verification fails -> automatic rollback")
    instance_id = _run_instance(client, {"Owner": "amanda", "Environment": "dev"})
    action = propose_stop_instance(instance_id, "us-east-1", reason="idle")
    print("Simulating a stop that did not actually take effect (e.g. AWS-side hiccup)...")
    failed_verification = VerificationResult(
        action_id=action.id,
        expected_state="stopped",
        actual_state="running",
        verified=False,
        attempts=settings.VERIFY_MAX_ATTEMPTS,
    )
    _print_model("Verification result", failed_verification)

    rollback: RollbackResult = rollback_action(action, failed_verification)
    _print_model("Rollback result", rollback)
    print("\n-> ESCALATED to a human." if rollback.escalated else "\n-> Rolled back successfully.")


def main() -> None:
    METRICS.reset()
    # Everything below runs against a moto-mocked AWS backend, so it's safe
    # to disable dry-run here and show real stop/start execution.
    settings.DRY_RUN = False
    with mock_aws():
        client = boto3.client("ec2", region_name="us-east-1")
        scenario_happy_path(client)
        scenario_github_evidence_raises_risk(client)
        scenario_prod_needs_approval(client)
        scenario_rollback_on_verify_failure(client)

    _print_header("METRICS SUMMARY")
    print(json.dumps(METRICS.summary(), indent=2))


if __name__ == "__main__":
    main()
