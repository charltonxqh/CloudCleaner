"""Real-AWS test run for the Safety/Actions/Evaluation scenarios that don't
depend on Slack (P1, P2, P3, P6, N1, N4, N5 from the demo test plan).

    uv run scripts/real_aws_test.py

Unlike scripts/demo_ec2_lifecycle.py, this hits a REAL AWS account - it
creates real (free-tier-eligible t2.micro) EC2 instances tagged
"cloudcleaner-test-*", exercises policy -> execute -> verify -> rollback
against them for real, then TERMINATES everything it created. Requires
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN / AWS_REGION
in app/.env.

Safety:
- DRY_RUN defaults to true (see cloudcleaner.config) - this script
  explicitly sets it False only for the duration of the run, and only
  ever acts on instances it just created itself (tracked in
  _created_instance_ids and cleaned up in `finally`).
- Every instance is tagged Name=cloudcleaner-test-* so it's unmistakable
  in the AWS console if cleanup ever needs to happen manually.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3

from cloudcleaner.config import settings
from cloudcleaner.graph.nodes.rollback import rollback_action
from cloudcleaner.graph.nodes.verify import verify_action
from cloudcleaner.policy import evaluate_action
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import PolicyDecision, ResourceContext, VerificationResult
from cloudcleaner.tools.aws.actions import execute_action, propose_start_instance, propose_stop_instance

# Free-tier eligible in most accounts/regions. Change if your account/region
# needs a different type or AMI.
INSTANCE_TYPE = "t2.micro"
NAME_PREFIX = "cloudcleaner-test"

_created_instance_ids: list[str] = []


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _print_model(label: str, model) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(json.loads(model.model_dump_json()), indent=2))


def _client():
    return boto3.client("ec2", region_name=settings.AWS_REGION)


def _latest_al2023_ami(client) -> str:
    resp = client.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(resp["Images"], key=lambda i: i["CreationDate"], reverse=True)
    if not images:
        raise RuntimeError("No Amazon Linux 2023 AMI found in this region/account")
    return images[0]["ImageId"]


def _launch(client, name: str, tags: dict[str, str]) -> str:
    ami_id = _latest_al2023_ami(client)
    all_tags = {"Name": name, **tags}
    resp = client.run_instances(
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        InstanceType=INSTANCE_TYPE,
        TagSpecifications=[
            {"ResourceType": "instance", "Tags": [{"Key": k, "Value": v} for k, v in all_tags.items()]}
        ],
    )
    instance_id = resp["Instances"][0]["InstanceId"]
    _created_instance_ids.append(instance_id)
    print(f"Launched {instance_id} ({name}), waiting for it to enter 'running'...")
    client.get_waiter("instance_running").wait(InstanceIds=[instance_id])
    print(f"  -> running.")
    return instance_id


def scenario_p1_happy_path(client) -> None:
    _print_header("P1: happy path - low-risk dev instance stops cleanly")
    instance_id = _launch(client, f"{NAME_PREFIX}-p1-happy-path", {"Owner": "amanda", "Environment": "dev"})
    ctx = ResourceContext(
        resource_id=instance_id, region=settings.AWS_REGION,
        tags={"Owner": "amanda", "Environment": "dev"}, state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=1),
        recent_activity=False, estimated_monthly_cost_usd=8.5,
    )
    action = propose_stop_instance(instance_id, settings.AWS_REGION, reason="P1 real-AWS test")
    policy_result = evaluate_action(action, ctx)
    _print_model("Policy result", policy_result)
    assert policy_result.decision == PolicyDecision.ALLOW, "expected ALLOW for low-risk dev instance"

    execution = execute_action(action)
    _print_model("Execution result", execution)

    verification = verify_action(action)
    _print_model("Verification result", verification)
    assert verification.verified, "expected the instance to actually reach 'stopped'"
    print("\n-> P1 PASSED")


def scenario_p2_start_undo(client, stopped_instance_id: str) -> None:
    _print_header("P2: start (undo) works on a stopped instance")
    action = propose_start_instance(stopped_instance_id, settings.AWS_REGION, reason="P2 real-AWS test")
    execution = execute_action(action)
    _print_model("Execution result", execution)
    verification = verify_action(action)
    _print_model("Verification result", verification)
    assert verification.verified, "expected the instance to actually reach 'running'"
    print("\n-> P2 PASSED")


def scenario_p3_idempotent_stop(client, running_instance_id: str) -> None:
    _print_header("P3: idempotent stop - stopping an already-stopped instance is a no-op")
    action = propose_stop_instance(running_instance_id, settings.AWS_REGION, reason="P3 setup: get it stopped")
    execute_action(action)
    verify_action(action)

    action2 = propose_stop_instance(running_instance_id, settings.AWS_REGION, reason="P3 real-AWS test: stop again")
    execution2 = execute_action(action2)
    _print_model("Second stop's execution result", execution2)
    assert execution2.idempotent_noop, "expected the second stop to be a no-op, not a real API call"
    print("\n-> P3 PASSED")


def scenario_p6_rollback_on_verify_failure() -> None:
    _print_header("P6: forced verification failure triggers automatic rollback")
    instance_id = "i-doesnotexist-forced-failure"  # deliberately invalid, forces verify to never succeed
    action = propose_stop_instance(instance_id, settings.AWS_REGION, reason="P6 real-AWS test")
    failed_verification = VerificationResult(
        action_id=action.id, expected_state="stopped", actual_state="unknown",
        verified=False, attempts=1,
    )
    rollback = rollback_action(action, failed_verification)
    _print_model("Rollback result", rollback)
    print(f"\n-> P6 result: escalated={rollback.escalated} (expected True - the target instance doesn't exist)")


def scenario_n1_cooldown_blocks(client) -> None:
    _print_header("N1: cooldown rule blocks a stop on a just-changed instance")
    instance_id = _launch(client, f"{NAME_PREFIX}-n1-cooldown", {"Owner": "amanda", "Environment": "dev"})
    ctx = ResourceContext(
        resource_id=instance_id, region=settings.AWS_REGION,
        tags={"Owner": "amanda", "Environment": "dev"}, state="running",
        last_state_change=datetime.now(timezone.utc),  # just changed - inside the 15-min cooldown
    )
    action = propose_stop_instance(instance_id, settings.AWS_REGION, reason="N1 real-AWS test")
    policy_result = evaluate_action(action, ctx)
    _print_model("Policy result", policy_result)
    assert policy_result.decision == PolicyDecision.BLOCK, "expected BLOCK from the cooldown rule"

    state = client.describe_instances(InstanceIds=[instance_id])
    state_name = state["Reservations"][0]["Instances"][0]["State"]["Name"]
    assert state_name == "running", "policy said BLOCK - the instance must not have been touched"
    print(f"\n-> N1 PASSED (AWS state confirms untouched: {state_name})")


def scenario_n4_nonexistent_instance() -> None:
    _print_header("N4: stopping a nonexistent instance fails cleanly, not a crash")
    action = propose_stop_instance("i-doesnotexist12345", settings.AWS_REGION, reason="N4 real-AWS test")
    execution = execute_action(action)
    _print_model("Execution result", execution)
    assert execution.status.value == "failed" and execution.error, "expected a clean FAILED result with an error message"
    print("\n-> N4 PASSED")


def _cleanup(client) -> None:
    if not _created_instance_ids:
        return
    _print_header("CLEANUP: terminating every instance this script created")
    print(_created_instance_ids)
    client.terminate_instances(InstanceIds=_created_instance_ids)
    client.get_waiter("instance_terminated").wait(InstanceIds=_created_instance_ids)
    print("All test instances terminated.")


def main() -> None:
    METRICS.reset()
    settings.DRY_RUN = False  # this script is explicitly testing real execution
    client = _client()

    try:
        scenario_p1_happy_path(client)
        # P1 leaves its instance stopped - reuse it for P2 (start) and P3 (idempotent stop).
        p1_instance_id = _created_instance_ids[0]
        scenario_p2_start_undo(client, p1_instance_id)
        scenario_p3_idempotent_stop(client, p1_instance_id)

        scenario_p6_rollback_on_verify_failure()
        scenario_n1_cooldown_blocks(client)
        scenario_n4_nonexistent_instance()
    finally:
        _cleanup(client)

    _print_header("METRICS SUMMARY")
    print(json.dumps(METRICS.summary(), indent=2))


if __name__ == "__main__":
    main()
