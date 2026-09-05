import re
from datetime import datetime, timezone

from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_ec2_client


def _tags_to_dict(tags: list[dict] | None) -> dict[str, str]:
    if not tags:
        return {}

    return {
        tag["Key"]: tag["Value"]
        for tag in tags
    }


def _last_state_change(instance: dict) -> datetime | None:
    state = instance["State"]["Name"]
    if state in ("pending", "running"):
        return instance.get("LaunchTime")

    reason = instance.get("StateTransitionReason") or ""
    match = re.search(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) GMT\)", reason)
    if not match:
        return None

    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def list_ec2_instances() -> list[CloudResource]:
    ec2 = get_ec2_client()

    paginator = ec2.get_paginator("describe_instances")

    resources = []

    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:

                tags = _tags_to_dict(
                    instance.get("Tags")
                )

                resource = CloudResource(
                    resource_id=instance["InstanceId"],
                    resource_type="ec2",
                    region=instance["Placement"]["AvailabilityZone"][:-1],
                    name=tags.get("Name"),
                    state=instance["State"]["Name"],
                    instance_type=instance["InstanceType"],
                    launch_time=instance["LaunchTime"].isoformat(),
                    last_state_change=_last_state_change(instance),
                    project=tags.get("Project"),
                    environment=tags.get("Environment"),
                    owner=tags.get("Owner"),
                    tags=tags,
                )

                resources.append(resource)

    return resources