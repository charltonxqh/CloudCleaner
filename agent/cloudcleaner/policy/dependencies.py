"""Discover what a resource is entangled with, and order the teardown.

AWS refuses deletions one blocker at a time. This builds the graph up front and
sorts it, so the whole sequence is known before anything runs.
"""

from collections import defaultdict

from cloudcleaner.schemas import CloudResource, TeardownStep

IRREVERSIBLE = {
    "terminate_instance", "delete_volume", "release_address", "delete_snapshot",
    "delete_nat_gateway", "delete_load_balancer", "delete_target_group",
    "delete_db_instance", "delete_cache_cluster", "deregister_image",
}


class DependencyCycle(Exception):
    pass


def _key(action: str, resource_id: str) -> str:
    return f"{action}:{resource_id}"


def build_steps(
    root: CloudResource,
    volumes: list[CloudResource],
    addresses: list[CloudResource],
    snapshot_first: bool = True,
) -> list[TeardownStep]:
    """Emit unordered steps with their dependency edges."""
    steps: list[TeardownStep] = []

    if root.resource_type in _BUILDERS:
        return _BUILDERS[root.resource_type](root, addresses, snapshot_first)

    attached = [v for v in volumes if v.attached_to == root.resource_id]
    eips = [a for a in addresses if a.attached_to == root.resource_id]

    # Volumes AWS will not clean up for us.
    orphaned_after = [v for v in attached if v.delete_on_termination is False]

    for eip in eips:
        assoc = eip.tags.get("AssociationId")
        if assoc:
            steps.append(TeardownStep(
                action="disassociate_address",
                resource_id=assoc,
                resource_type="eip",
                reason=f"{eip.public_ip} is attached to {root.resource_id}",
                reversible=True,
            ))
        steps.append(TeardownStep(
            action="release_address",
            resource_id=eip.resource_id,
            resource_type="eip",
            reason="public IPv4 bills hourly whether or not it is in use",
            monthly_saving=eip.estimated_monthly_cost or 0.0,
            reversible=False,
            depends_on=[_key("disassociate_address", assoc)] if assoc else [],
        ))

    if snapshot_first:
        for vol in orphaned_after:
            steps.append(TeardownStep(
                action="snapshot_volume",
                resource_id=vol.resource_id,
                resource_type="ebs",
                reason="restore point before an irreversible delete",
                reversible=True,
            ))

    if root.resource_type == "ebs" and root.attached_to is None:
        if snapshot_first:
            steps.append(TeardownStep(
                action="snapshot_volume", resource_id=root.resource_id, resource_type="ebs",
                reason="restore point before an irreversible delete", reversible=True,
            ))
        steps.append(TeardownStep(
            action="delete_volume", resource_id=root.resource_id, resource_type="ebs",
            reason=f"unattached {root.size_gb}GB volume, billing since creation",
            monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
            depends_on=[_key("snapshot_volume", root.resource_id)] if snapshot_first else [],
        ))
        return steps

    if root.resource_type == "eip" and root.attached_to is None:
        steps.append(TeardownStep(
            action="release_address", resource_id=root.resource_id, resource_type="eip",
            reason="unassociated public IPv4, billing hourly",
            monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        ))
        return steps

    if root.resource_type == "ec2":
        steps.append(TeardownStep(
            action="terminate_instance",
            resource_id=root.resource_id,
            resource_type="ec2",
            reason="idle instance",
            monthly_saving=root.estimated_monthly_cost or 0.0,
            reversible=False,
            depends_on=[_key("snapshot_volume", v.resource_id) for v in orphaned_after],
        ))

    for vol in orphaned_after:
        steps.append(TeardownStep(
            action="delete_volume",
            resource_id=vol.resource_id,
            resource_type="ebs",
            reason="DeleteOnTermination=false, so it survives the instance and keeps billing",
            monthly_saving=vol.estimated_monthly_cost or 0.0,
            reversible=False,
            depends_on=[_key("terminate_instance", root.resource_id)],
        ))

    return steps


def order_steps(steps: list[TeardownStep]) -> list[TeardownStep]:
    """Kahn's algorithm. Raises DependencyCycle if the graph cannot be linearised."""
    by_key = {_key(s.action, s.resource_id): s for s in steps}

    indegree = {k: 0 for k in by_key}
    dependents = defaultdict(list)

    for key, step in by_key.items():
        for dep in step.depends_on:
            if dep not in by_key:
                continue
            indegree[key] += 1
            dependents[dep].append(key)

    ready = sorted(k for k, d in indegree.items() if d == 0)
    ordered: list[TeardownStep] = []

    while ready:
        key = ready.pop(0)
        step = by_key[key]
        step.order = len(ordered) + 1
        ordered.append(step)

        for nxt in dependents[key]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort()

    if len(ordered) != len(by_key):
        unresolved = sorted(set(by_key) - {_key(s.action, s.resource_id) for s in ordered})
        raise DependencyCycle(f"cannot order: {unresolved}")

    return ordered


def resolve(root, volumes, addresses, snapshot_first: bool = True) -> list[TeardownStep]:
    return order_steps(build_steps(root, volumes, addresses, snapshot_first))


# --- Types whose teardown is an ordered chain rather than a single delete ---


def _nat_steps(root, addresses, snapshot_first) -> list[TeardownStep]:
    """Routes first, then the gateway, then its address.

    AWS rejects delete_nat_gateway while a route table still points at it, and
    the address cannot be released until the gateway that holds it is gone.
    """
    steps = [
        TeardownStep(
            action="delete_route", resource_id=rtb, resource_type="route_table",
            reason=f"0.0.0.0/0 in {rtb} still points at {root.resource_id}",
            reversible=True,
        )
        for rtb in root.route_table_ids
    ]

    steps.append(TeardownStep(
        action="delete_nat_gateway", resource_id=root.resource_id, resource_type="nat",
        reason="NAT gateway bills hourly whether or not any traffic flows through it",
        monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        depends_on=[_key("delete_route", rtb) for rtb in root.route_table_ids],
    ))

    owned = root.address_ids or [
        a.resource_id for a in addresses if a.attached_to == root.resource_id
    ]
    for alloc in owned:
        steps.append(TeardownStep(
            action="release_address", resource_id=alloc, resource_type="eip",
            reason="the gateway's public IPv4 keeps billing once the gateway is gone",
            monthly_saving=next(
                (a.estimated_monthly_cost or 0.0 for a in addresses if a.resource_id == alloc),
                0.0,
            ),
            reversible=False,
            depends_on=[_key("delete_nat_gateway", root.resource_id)],
        ))

    return steps


def _elb_steps(root, addresses, snapshot_first) -> list[TeardownStep]:
    """Listeners, then the balancer, then the target groups it was using."""
    steps = [
        TeardownStep(
            action="delete_listener", resource_id=arn, resource_type="listener",
            reason="listener holds a reference to the balancer", reversible=True,
        )
        for arn in root.listener_ids
    ]

    steps.append(TeardownStep(
        action="delete_load_balancer", resource_id=root.resource_id, resource_type="elb",
        reason="balancer bills its hourly base rate with no healthy targets behind it",
        monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        depends_on=[_key("delete_listener", arn) for arn in root.listener_ids],
    ))

    for arn in root.target_group_ids:
        steps.append(TeardownStep(
            action="delete_target_group", resource_id=arn, resource_type="target_group",
            reason="target group cannot be deleted while a listener still forwards to it",
            reversible=False,
            depends_on=[_key("delete_load_balancer", root.resource_id)],
        ))

    return steps


def _rds_steps(root, addresses, snapshot_first) -> list[TeardownStep]:
    """Deletion protection off, final snapshot taken, then the instance."""
    depends = []

    if root.deletion_protection:
        steps = [TeardownStep(
            action="disable_deletion_protection", resource_id=root.resource_id,
            resource_type="rds",
            reason="DeletionProtection=true blocks the delete outright",
            reversible=True,
        )]
        depends.append(_key("disable_deletion_protection", root.resource_id))
    else:
        steps = []

    if snapshot_first:
        steps.append(TeardownStep(
            action="snapshot_database", resource_id=root.resource_id, resource_type="rds",
            reason="final snapshot before an irreversible delete", reversible=True,
        ))
        depends.append(_key("snapshot_database", root.resource_id))

    steps.append(TeardownStep(
        action="delete_db_instance", resource_id=root.resource_id, resource_type="rds",
        reason=(
            f"stopped {root.engine or 'database'} still bills for {root.size_gb or 0}GB of "
            "storage, and AWS restarts it automatically after 7 days"
        ),
        monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        depends_on=depends,
    ))

    return steps


def _cache_steps(root, addresses, snapshot_first) -> list[TeardownStep]:
    """Redis can be snapshotted first; memcached cannot, so nothing is promised."""
    steps = []
    depends = []

    if snapshot_first and (root.engine or "").lower() == "redis":
        steps.append(TeardownStep(
            action="snapshot_cache", resource_id=root.resource_id, resource_type="cache",
            reason="final snapshot before an irreversible delete", reversible=True,
        ))
        depends.append(_key("snapshot_cache", root.resource_id))

    steps.append(TeardownStep(
        action="delete_cache_cluster", resource_id=root.resource_id, resource_type="cache",
        reason=(
            f"{root.node_count} x {root.instance_type} cache node(s) bill continuously; "
            "ElastiCache has no stopped state"
        ),
        monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        depends_on=depends,
    ))

    return steps


def _snapshot_steps(root, addresses, snapshot_first) -> list[TeardownStep]:
    """Any AMI built on the snapshot has to be deregistered before it can go."""
    steps = [
        TeardownStep(
            action="deregister_image", resource_id=image, resource_type="ami",
            reason=f"{image} is built on {root.resource_id} and blocks its deletion",
            reversible=False,
        )
        for image in root.image_ids
    ]

    steps.append(TeardownStep(
        action="delete_snapshot", resource_id=root.resource_id, resource_type="snapshot",
        reason=f"{root.size_gb or 0}GB snapshot billing since it was taken",
        monthly_saving=root.estimated_monthly_cost or 0.0, reversible=False,
        depends_on=[_key("deregister_image", i) for i in root.image_ids],
    ))

    return steps


_BUILDERS = {
    "nat": _nat_steps,
    "elb": _elb_steps,
    "rds": _rds_steps,
    "cache": _cache_steps,
    "snapshot": _snapshot_steps,
}
