from cloudcleaner.config import DRY_RUN
from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.storage.repository import record_run


def record_node(state: CloudCleanerState):
    run = record_run(
        resource=state["resource"],
        recommendation=state.get("recommendation"),
        plan=state.get("plan"),
        approval=state.get("approval"),
        action_results=state.get("action_results"),
        verification_passed=state.get("verification_passed"),
        dry_run=DRY_RUN,
    )
    log.emit("record", "decision", run["resource_id"],
             f"run {run['run_id'][:8]} saved: {run['executed']} actions, "
             f"${run['monthly_saving']}/mo")
    return {"run_id": run["run_id"]}
