from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.tools.aws.cost import (
    instance_cost,
    instance_cost_if_stopped,
    instance_monthly_saving_if_stopped,
)
from cloudcleaner.tools.provider import list_ec2_instances, list_elastic_ips, list_volumes


def _enrich(instance, volumes, eips):
    attached = [v for v in volumes if v.attached_to == instance.resource_id]
    gb = sum(v.size_gb or 0 for v in attached)
    has_ip = bool(instance.public_ip) or any(e.attached_to == instance.resource_id for e in eips)

    cost, residual = instance_cost(instance.state, instance.instance_type, gb, has_ip)
    cost_if_stopped = instance_cost_if_stopped(gb, has_ip)
    saving_if_stopped = instance_monthly_saving_if_stopped(
        instance.state, instance.instance_type, gb, has_ip
    )
    instance.volume_ids = [v.resource_id for v in attached]
    instance.estimated_monthly_cost = cost
    instance.monthly_cost_if_stopped = cost_if_stopped
    instance.monthly_saving_if_stopped = saving_if_stopped
    instance.billing_while_stopped = residual
    return instance


def _waste_score(r):
    """Rank by wasted spend, not total spend: a busy prod box is expensive, not wasteful."""
    return (
        r.billing_while_stopped,
        r.state in ("stopped", "available", "unassociated"),
        r.attached_to is None and r.resource_type in ("ebs", "eip"),
        r.estimated_monthly_cost or 0,
    )


def detect_node(state: CloudCleanerState):
    if state.get("resource") is not None:
        # Seeded by the API with a cached scan: still a new run, so the trail
        # starts clean rather than inheriting the previous request's events.
        log.start()
        return {}

    log.start()

    instances = list_ec2_instances()
    volumes = list_volumes()
    eips = list_elastic_ips()

    candidates = [_enrich(i, volumes, eips) for i in instances if i.state != "terminated"]
    orphans = [v for v in volumes if v.attached_to is None]
    orphans += [e for e in eips if e.state == "unassociated"]

    log.emit("detect", "finding", "-",
             f"{len(candidates)} instances, {len(orphans)} orphaned resources")

    for r in candidates:
        if r.billing_while_stopped:
            log.emit("detect", "finding", r.resource_id,
                     f"stopped but still billing ${r.estimated_monthly_cost}/mo",
                     cost=r.estimated_monthly_cost)

    if not candidates and not orphans:
        log.emit("detect", "decision", "-", "account is clean, nothing to investigate")
        return {"inventory": [], "orphans": [], "volumes": [], "addresses": [],
                "done_reason": "nothing to investigate"}

    target = max(candidates + orphans, key=_waste_score)
    log.emit("detect", "handoff", target.resource_id, "selected highest-waste candidate")

    return {
        "inventory": candidates,
        "orphans": orphans,
        "volumes": volumes,
        "addresses": eips,
        "resource": target,
    }
