from cloudcleaner.tools.aws.client import get_ec2_client


class ActionResult(dict):
    pass


def _result(action: str, resource_id: str, ok: bool, detail: str = "", dry_run: bool = False):
    return ActionResult(
        action=action,
        resource_id=resource_id,
        ok=ok,
        detail=detail,
        dry_run=dry_run,
    )


def stop_instance(instance_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("stop_instance", instance_id, True, "dry run", True)
    ec2 = get_ec2_client()
    resp = ec2.stop_instances(InstanceIds=[instance_id])
    state = resp["StoppingInstances"][0]["CurrentState"]["Name"]
    return _result("stop_instance", instance_id, True, state)


def terminate_instance(instance_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("terminate_instance", instance_id, True, "dry run", True)
    ec2 = get_ec2_client()
    resp = ec2.terminate_instances(InstanceIds=[instance_id])
    state = resp["TerminatingInstances"][0]["CurrentState"]["Name"]
    return _result("terminate_instance", instance_id, True, state)


def snapshot_volume(volume_id: str, description: str = "", dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("snapshot_volume", volume_id, True, "dry run", True)
    ec2 = get_ec2_client()
    resp = ec2.create_snapshot(
        VolumeId=volume_id,
        Description=description or f"cloudcleaner restore point for {volume_id}",
        TagSpecifications=[{
            "ResourceType": "snapshot",
            "Tags": [{"Key": "CreatedBy", "Value": "cloudcleaner"}],
        }],
    )
    return _result("snapshot_volume", volume_id, True, resp["SnapshotId"])


def delete_volume(volume_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("delete_volume", volume_id, True, "dry run", True)
    get_ec2_client().delete_volume(VolumeId=volume_id)
    return _result("delete_volume", volume_id, True, "deleted")


def disassociate_address(association_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("disassociate_address", association_id, True, "dry run", True)
    get_ec2_client().disassociate_address(AssociationId=association_id)
    return _result("disassociate_address", association_id, True, "disassociated")


def release_address(allocation_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("release_address", allocation_id, True, "dry run", True)
    get_ec2_client().release_address(AllocationId=allocation_id)
    return _result("release_address", allocation_id, True, "released")


def delete_snapshot(snapshot_id: str, dry_run: bool = True) -> ActionResult:
    if dry_run:
        return _result("delete_snapshot", snapshot_id, True, "dry run", True)
    get_ec2_client().delete_snapshot(SnapshotId=snapshot_id)
    return _result("delete_snapshot", snapshot_id, True, "deleted")


ACTIONS = {
    "stop_instance": stop_instance,
    "terminate_instance": terminate_instance,
    "snapshot_volume": snapshot_volume,
    "delete_volume": delete_volume,
    "disassociate_address": disassociate_address,
    "release_address": release_address,
    "delete_snapshot": delete_snapshot,
}
