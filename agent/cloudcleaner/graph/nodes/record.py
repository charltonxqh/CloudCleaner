from cloudcleaner.config import DRY_RUN
from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.storage.repository import record_run


def record_node(state: CloudCleanerState):
    resource = state["resource"]
    actions = state.get("action_results") or []
    plan = state.get("plan")

    # Emitted before the run is written, so this event is flushed with the run
    # it describes rather than landing in the next one's buffer.
    log.emit("record", "decision", resource.resource_id,
             f"recording run: {len([a for a in actions if a.get('ok')])} actions, "
             f"${plan.total_monthly_saving if plan else 0.0}/mo")

    run = record_run(
        resource=resource,
        recommendation=state.get("recommendation"),
        plan=plan,
        approval=state.get("approval"),
        action_results=actions,
        verification_passed=state.get("verification_passed"),
        dry_run=DRY_RUN,
    )
    return {"run_id": run["run_id"]}
