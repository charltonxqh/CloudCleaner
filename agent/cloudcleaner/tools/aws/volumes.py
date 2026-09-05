from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_ec2_client
from cloudcleaner.tools.aws.cost import ebs_cost, snapshot_cost


def _tags(tags):
    return {t["Key"]: t["Value"] for t in (tags or [])}


def list_volumes(only_unattached: bool = False) -> list[CloudResource]:
    ec2 = get_ec2_client()
    filters = [{"Name": "status", "Values": ["available"]}] if only_unattached else []

    out = []
    for page in ec2.get_paginator("describe_volumes").paginate(Filters=filters):
        for vol in page["Volumes"]:
            tags = _tags(vol.get("Tags"))
            attachments = vol.get("Attachments") or []
            attached_to = attachments[0]["InstanceId"] if attachments else None
            dot = attachments[0].get("DeleteOnTermination") if attachments else None

            out.append(CloudResource(
                resource_id=vol["VolumeId"],
                resource_type="ebs",
                region=vol["AvailabilityZone"][:-1],
                name=tags.get("Name"),
                state=vol["State"],
                size_gb=vol["Size"],
                attached_to=attached_to,
                delete_on_termination=dot,
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=ebs_cost(vol["Size"], vol.get("VolumeType")),
                billing_while_stopped=True,
                tags=tags,
            ))
    return out


def list_snapshots(owned_by_self: bool = True) -> list[CloudResource]:
    ec2 = get_ec2_client()
    kwargs = {"OwnerIds": ["self"]} if owned_by_self else {}

    out = []
    for page in ec2.get_paginator("describe_snapshots").paginate(**kwargs):
        for snap in page["Snapshots"]:
            tags = _tags(snap.get("Tags"))
            out.append(CloudResource(
                resource_id=snap["SnapshotId"],
                resource_type="snapshot",
                region="",
                name=tags.get("Name"),
                state=snap["State"],
                size_gb=snap["VolumeSize"],
                attached_to=snap.get("VolumeId"),
                launch_time=snap["StartTime"].isoformat(),
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=snapshot_cost(snap["VolumeSize"]),
                billing_while_stopped=True,
                tags=tags,
            ))
    return out


def volumes_for_instance(instance_id: str) -> list[CloudResource]:
    return [v for v in list_volumes() if v.attached_to == instance_id]
