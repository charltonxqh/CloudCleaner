from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.tools.aws.cost import (
    instance_cost,
    instance_cost_if_stopped,
    instance_monthly_saving_if_stopped,
)
from cloudcleaner.tools.provider import (
    list_cache_clusters,
    list_ec2_instances,
    list_elastic_ips,
    list_load_balancers,
    list_nat_gateways,
    list_rds_instances,
    list_snapshots,
    list_volumes,
)


def _safe(label: str, fn):
    try:
        return fn()
    except Exception as e:
        log.emit("detect", "error", "-", f"could not list {label}: {e}")
        return []


def _type_count(resources) -> int:
    return len({r.resource_type for r in resources})


def _owned_by_gateway(eip, gateways) -> bool:
    """An address held by a NAT gateway is not an orphan; it is part of that teardown."""
    return any(eip.resource_id in (g.address_ids or []) for g in gateways)


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


# Types that keep billing with no way to pause them. Deleting is the only lever,
# so their whole monthly cost counts as waste once they are found to be idle.
UNPAUSABLE = ("nat", "elb", "cache", "snapshot")


def _wasted_monthly(r) -> float:
    """Dollars with nothing to show for them, not total spend."""
    cost = r.estimated_monthly_cost or 0.0

    if r.resource_type in UNPAUSABLE:
        return cost
    if r.billing_while_stopped:
        return cost
    if r.attached_to is None and r.resource_type in ("ebs", "eip"):
        return cost
    return 0.0


def _waste_score(r):
    """Rank by wasted spend, not total spend: a busy prod box is expensive, not wasteful."""
    return (_wasted_monthly(r), r.estimated_monthly_cost or 0.0)


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

    # Each of these can fail independently on a real account (a region with no
    # RDS, a missing IAM permission). One missing service must not blank the scan.
    gateways = _safe("nat gateways", list_nat_gateways)
    balancers = _safe("load balancers", list_load_balancers)
    databases = _safe("rds instances", list_rds_instances)
    caches = _safe("cache clusters", list_cache_clusters)
    snapshots = _safe("snapshots", list_snapshots)

    candidates = [_enrich(i, volumes, eips) for i in instances if i.state != "terminated"]
    candidates += gateways + balancers + databases + caches

    orphans = [v for v in volumes if v.attached_to is None]
    orphans += [e for e in eips if e.state == "unassociated" and not _owned_by_gateway(e, gateways)]
    orphans += snapshots

    log.emit("detect", "finding", "-",
             f"{len(candidates)} active resources across {_type_count(candidates + orphans)} "
             f"types, {len(orphans)} orphaned")

    for r in candidates + orphans:
        if _wasted_monthly(r) and r.billing_while_stopped:
            log.emit("detect", "finding", r.resource_id,
                     f"stopped but still billing ${r.estimated_monthly_cost}/mo",
                     cost=r.estimated_monthly_cost)

    if not candidates and not orphans:
        log.emit("detect", "decision", "-", "account is clean, nothing to investigate")
        return {"inventory": [], "orphans": [], "volumes": [], "addresses": [],
                "done_reason": "nothing to investigate"}

    target = max(candidates + orphans, key=_waste_score)
    log.emit("detect", "handoff", target.resource_id,
             f"selected highest-waste candidate (${_wasted_monthly(target)}/mo wasted)",
             cost=_wasted_monthly(target))

    return {
        "inventory": candidates,
        "orphans": orphans,
        "volumes": volumes,
        "addresses": eips,
        "resource": target,
    }
