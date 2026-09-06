"""Load balancers. A balancer with no healthy targets still bills the base rate."""

from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_elbv2_client
from cloudcleaner.tools.aws.cost import load_balancer_cost


def _arn_name(arn: str) -> str:
    return arn.rsplit("/", 1)[-1]


def list_load_balancers() -> list[CloudResource]:
    elb = get_elbv2_client()

    out = []
    for page in elb.get_paginator("describe_load_balancers").paginate():
        for lb in page["LoadBalancers"]:
            arn = lb["LoadBalancerArn"]

            try:
                tags = {
                    t["Key"]: t["Value"]
                    for d in elb.describe_tags(ResourceArns=[arn])["TagDescriptions"]
                    for t in d.get("Tags", [])
                }
            except Exception:
                tags = {}

            listeners = [
                x["ListenerArn"]
                for x in elb.describe_listeners(LoadBalancerArn=arn).get("Listeners", [])
            ]
            groups = [
                g["TargetGroupArn"]
                for g in elb.describe_target_groups(LoadBalancerArn=arn).get("TargetGroups", [])
            ]

            out.append(CloudResource(
                resource_id=arn,
                resource_type="elb",
                region="",
                name=lb.get("LoadBalancerName"),
                state=lb.get("State", {}).get("Code"),
                instance_type=lb.get("Type"),
                vpc_id=lb.get("VpcId"),
                launch_time=lb["CreatedTime"].isoformat() if lb.get("CreatedTime") else None,
                listener_ids=listeners,
                target_group_ids=groups,
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=load_balancer_cost(lb.get("Type")),
                billing_while_stopped=True,
                tags=tags,
            ))
    return out


def healthy_target_count(target_group_arns: list[str]) -> int:
    elb = get_elbv2_client()
    total = 0
    for arn in target_group_arns:
        health = elb.describe_target_health(TargetGroupArn=arn).get("TargetHealthDescriptions", [])
        total += sum(1 for h in health if h["TargetHealth"]["State"] == "healthy")
    return total
