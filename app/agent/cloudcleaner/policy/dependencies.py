"""Discover what a resource is entangled with, and order the teardown.

AWS refuses deletions one blocker at a time. This builds the graph up front and
sorts it, so the whole sequence is known before anything runs.
"""

from collections import defaultdict

from cloudcleaner.schemas import CloudResource, TeardownStep

IRREVERSIBLE = {"terminate_instance", "delete_volume", "release_address", "delete_snapshot"}


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
