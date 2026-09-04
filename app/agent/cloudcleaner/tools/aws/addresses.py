from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_ec2_client
from cloudcleaner.tools.aws.cost import public_ipv4_cost


def list_elastic_ips() -> list[CloudResource]:
    ec2 = get_ec2_client()
    addresses = ec2.describe_addresses()["Addresses"]

    out = []
    for addr in addresses:
        tags = {t["Key"]: t["Value"] for t in (addr.get("Tags") or [])}
        associated = bool(addr.get("AssociationId"))

        out.append(CloudResource(
            resource_id=addr["AllocationId"],
            resource_type="eip",
            region="",
            name=tags.get("Name"),
            state="associated" if associated else "unassociated",
            public_ip=addr.get("PublicIp"),
            attached_to=addr.get("InstanceId"),
            project=tags.get("Project"),
            environment=tags.get("Environment"),
            owner=tags.get("Owner"),
            estimated_monthly_cost=public_ipv4_cost(),
            billing_while_stopped=True,
            tags={**tags, "AssociationId": addr.get("AssociationId", "")},
        ))
    return out
