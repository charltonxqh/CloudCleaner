from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy import safety
from cloudcleaner.policy.dependencies import DependencyCycle, resolve
from cloudcleaner.schemas import RestoreRecipe, TeardownPlan


def _restore_recipe(resource, volumes) -> RestoreRecipe:
    return RestoreRecipe(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        instance_type=resource.instance_type,
        availability_zone=resource.region,
        public_ip=resource.public_ip,
        tags=resource.tags,
        note="Snapshot IDs are filled in at execution time.",
    )


def plan_node(state: CloudCleanerState):
    resource = state["resource"]
    rid = resource.resource_id

    if state.get("force_plan"):
        log.emit("plan", "decision", rid, "human overrode the verdict, planning anyway")

    blocks = safety.check(resource, allow_untagged=True)
    if blocks:
        log.emit("plan", "skip", rid, f"blocked by safety policy: {'; '.join(blocks)}")
        return {"plan": TeardownPlan(root_resource_id=rid, blocked=blocks)}

    volumes = state.get("volumes") or []
    addresses = state.get("addresses") or []

    try:
        steps = resolve(resource, volumes, addresses)
    except DependencyCycle as e:
        log.emit("plan", "error", rid, str(e))
        return {"plan": TeardownPlan(root_resource_id=rid, blocked=[str(e)])}

    plan = TeardownPlan(
        root_resource_id=rid,
        steps=steps,
        restore=_restore_recipe(resource, volumes),
    )

    log.emit("plan", "decision", rid,
             f"{len(steps)} ordered steps, ${plan.total_monthly_saving}/mo, "
             f"{len(plan.irreversible_steps)} irreversible",
             saving=plan.total_monthly_saving)

    return {"plan": plan}
