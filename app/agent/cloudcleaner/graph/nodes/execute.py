from cloudcleaner.config import DRY_RUN
from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.tools.aws.actions import ACTIONS


def execute_node(state: CloudCleanerState):
    plan = state["plan"]
    approved = set(state["approval"].approved_resource_ids or [])
    results = []
    snapshots = {}

    for step in plan.steps:
        if plan.root_resource_id not in approved:
            log.emit("execute", "skip", step.resource_id, "root resource not approved")
            break

        fn = ACTIONS.get(step.action)
        if fn is None:
            log.emit("execute", "error", step.resource_id, f"unknown action {step.action}")
            continue

        try:
            result = fn(step.resource_id, dry_run=DRY_RUN)
        except Exception as e:
            log.emit("execute", "error", step.resource_id, f"{step.action} failed: {e}")
            results.append({"action": step.action, "resource_id": step.resource_id,
                            "ok": False, "detail": str(e), "dry_run": DRY_RUN})
            break

        if step.action == "snapshot_volume" and not DRY_RUN:
            snapshots[step.resource_id] = result["detail"]

        log.emit("execute", "action", step.resource_id,
                 f"{step.order}. {step.action} -> {result['detail']}", dry_run=result["dry_run"])
        results.append(dict(result))

    if plan.restore and snapshots:
        plan.restore.volume_snapshots = snapshots

    return {"action_results": results}
