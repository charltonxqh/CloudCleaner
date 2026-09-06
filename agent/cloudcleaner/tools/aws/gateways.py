"""NAT gateways: the most expensive thing people forget, at $32.85/mo idle."""

from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_ec2_client
from cloudcleaner.tools.aws.cost import nat_gateway_cost


def _tags(tags):
    return {t["Key"]: t["Value"] for t in (tags or [])}


def _route_tables_using(ec2, nat_id: str) -> list[str]:
    resp = ec2.describe_route_tables(
        Filters=[{"Name": "route.nat-gateway-id", "Values": [nat_id]}]
    )
    return [rt["RouteTableId"] for rt in resp["RouteTables"]]


def list_nat_gateways() -> list[CloudResource]:
    ec2 = get_ec2_client()

    out = []
    for page in ec2.get_paginator("describe_nat_gateways").paginate():
        for nat in page["NatGateways"]:
            if nat["State"] in ("deleted", "deleting"):
                continue

            tags = _tags(nat.get("Tags"))
            addresses = nat.get("NatGatewayAddresses") or []

            out.append(CloudResource(
                resource_id=nat["NatGatewayId"],
                resource_type="nat",
                region="",
                name=tags.get("Name"),
                state=nat["State"],
                vpc_id=nat.get("VpcId"),
                subnet_id=nat.get("SubnetId"),
                attached_to=nat.get("SubnetId"),
                launch_time=nat["CreateTime"].isoformat() if nat.get("CreateTime") else None,
                public_ip=addresses[0].get("PublicIp") if addresses else None,
                address_ids=[a["AllocationId"] for a in addresses if a.get("AllocationId")],
                route_table_ids=_route_tables_using(ec2, nat["NatGatewayId"]),
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=nat_gateway_cost(),
                # There is no "stop" for a NAT gateway. It bills until deleted.
                billing_while_stopped=True,
                tags=tags,
            ))
    return out
