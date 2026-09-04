from cloudcleaner.config import DRY_RUN
from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.tools.aws.client import get_ec2_client

EXPECTED = {
    "stop_instance": {"stopping", "stopped"},
    "terminate_instance": {"shutting-down", "terminated"},
}


def _instance_state(instance_id: str) -> str | None:
    resp = get_ec2_client().describe_instances(InstanceIds=[instance_id])
    for r in resp["Reservations"]:
        for i in r["Instances"]:
            return i["State"]["Name"]
    return None


def verify_node(state: CloudCleanerState):
    results = state.get("action_results") or []
    if not results:
        return {"verification_passed": False}

    if DRY_RUN:
        log.emit("verify", "decision", "-", "dry run, nothing to verify")
        return {"verification_passed": True}

    ok = True
    for r in results:
        expected = EXPECTED.get(r["action"])
        if not expected:
            continue
        actual = _instance_state(r["resource_id"])
        passed = actual in expected
        ok = ok and passed
        log.emit("verify", "decision", r["resource_id"],
                 f"state={actual} expected={sorted(expected)} passed={passed}")

    return {"verification_passed": ok}
