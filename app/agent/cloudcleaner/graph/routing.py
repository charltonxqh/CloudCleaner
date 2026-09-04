from cloudcleaner.graph.state import CloudCleanerState


def after_detect(state: CloudCleanerState) -> str:
    return "end" if state.get("done_reason") else "investigate"


def after_assess(state: CloudCleanerState) -> str:
    if state.get("force_plan"):
        return "plan"

    rec = state.get("recommendation")
    if rec is None or rec.action in ("keep", "investigate_more"):
        return "record"
    return "plan"


def after_plan(state: CloudCleanerState) -> str:
    plan = state.get("plan")
    if plan is None or plan.blocked or not plan.steps:
        return "record"
    return "approval"


def after_approval(state: CloudCleanerState) -> str:
    approval = state.get("approval")
    return "execute" if approval and approval.decision == "approve" else "record"
