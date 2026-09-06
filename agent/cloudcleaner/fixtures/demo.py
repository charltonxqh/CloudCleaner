"""Offline demo stack. Shapes match real describe_* responses so the graph cannot tell."""

from cloudcleaner.schemas import CloudResource, GitHubEvidence

INSTANCES = [
    CloudResource(
        resource_id="i-0abc123def456789", resource_type="ec2", region="us-east-1",
        name="payments-poc", state="stopped", instance_type="t3.micro",
        launch_time="2026-06-14T09:12:00+00:00",
        project="payments", environment="dev", owner="hayden",
        tags={"Name": "payments-poc", "Project": "payments",
              "Environment": "dev", "Owner": "hayden", "Repo": "wkxcass/cloudcleaner-demo-payments"},
    ),
    CloudResource(
        resource_id="i-0999prod888", resource_type="ec2", region="us-east-1",
        name="checkout-api", state="running", instance_type="t3.medium",
        launch_time="2026-02-01T08:00:00+00:00",
        project="checkout", environment="prod", owner="team-payments",
        tags={"Name": "checkout-api", "Environment": "prod", "Project": "checkout"},
    ),
]

VOLUMES = [
    CloudResource(
        resource_id="vol-0a9b8c7d6", resource_type="ebs", region="us-east-1",
        state="in-use", size_gb=16, attached_to="i-0abc123def456789",
        delete_on_termination=False, estimated_monthly_cost=1.28,
        billing_while_stopped=True, tags={"Name": "payments-poc-root"},
    ),
    CloudResource(
        resource_id="vol-0orphan11", resource_type="ebs", region="us-east-1",
        state="available", size_gb=100, estimated_monthly_cost=8.0,
        billing_while_stopped=True, tags={"Name": "old-migration-scratch"},
    ),
    CloudResource(
        resource_id="vol-0prod222", resource_type="ebs", region="us-east-1",
        state="in-use", size_gb=50, attached_to="i-0999prod888",
        delete_on_termination=True, estimated_monthly_cost=4.0,
        billing_while_stopped=True, tags={"Name": "checkout-api-root"},
    ),
]

ADDRESSES = [
    CloudResource(
        resource_id="eipalloc-0f2e3d4", resource_type="eip", region="us-east-1",
        state="associated", public_ip="54.211.8.12", attached_to="i-0abc123def456789",
        estimated_monthly_cost=3.65, billing_while_stopped=True,
        tags={"Name": "payments-poc-ip", "AssociationId": "eipassoc-0c1b2a3"},
    ),
    CloudResource(
        resource_id="eipalloc-0unused9", resource_type="eip", region="us-east-1",
        state="unassociated", public_ip="3.91.44.7",
        estimated_monthly_cost=3.65, billing_while_stopped=True, tags={},
    ),
]

# --- The abandoned "payments" VPC ---
# One project was wound down and nobody deleted its plumbing. Every resource
# below still bills, and none of them can be removed in an arbitrary order.

NAT_GATEWAYS = [
    CloudResource(
        resource_id="nat-0d1e2f3a4b5c6", resource_type="nat", region="us-east-1",
        name="payments-dev-nat", state="available",
        vpc_id="vpc-0payments1", subnet_id="subnet-0public9",
        attached_to="subnet-0public9",
        launch_time="2026-05-02T11:20:00+00:00",
        public_ip="52.20.145.3", address_ids=["eipalloc-0nat7788"],
        route_table_ids=["rtb-0private1", "rtb-0private2"],
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=32.85, billing_while_stopped=True,
        tags={"Name": "payments-dev-nat", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
]

LOAD_BALANCERS = [
    CloudResource(
        resource_id=(
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "loadbalancer/app/payments-dev-alb/8f1c2d3e4a5b6c7d"
        ),
        resource_type="elb", region="us-east-1",
        name="payments-dev-alb", state="active", instance_type="application",
        vpc_id="vpc-0payments1",
        launch_time="2026-05-02T11:34:00+00:00",
        listener_ids=[
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "listener/app/payments-dev-alb/8f1c2d3e4a5b6c7d/1a2b3c4d"
        ],
        target_group_ids=[
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
            "targetgroup/payments-dev-tg/9e8d7c6b5a4f3e2d"
        ],
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=16.43, billing_while_stopped=True,
        tags={"Name": "payments-dev-alb", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
]

DATABASES = [
    CloudResource(
        # Stopped, and still charged for 20GB of storage. AWS will also restart
        # it automatically 7 days after it was stopped.
        resource_id="payments-dev-db", resource_type="rds", region="us-east-1",
        name="payments-dev-db", state="stopped",
        instance_type="db.t3.small", engine="postgres", size_gb=20,
        vpc_id="vpc-0payments1",
        launch_time="2026-05-02T12:02:00+00:00",
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=2.3, monthly_cost_if_stopped=2.3,
        monthly_saving_if_stopped=0.0, billing_while_stopped=True,
        tags={"Name": "payments-dev-db", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
    CloudResource(
        resource_id="checkout-prod-db", resource_type="rds", region="us-east-1",
        name="checkout-prod-db", state="available",
        instance_type="db.m5.large", engine="postgres", size_gb=200,
        multi_az=True, vpc_id="vpc-0checkout2",
        launch_time="2026-01-11T09:00:00+00:00",
        project="checkout", environment="prod", owner="team-payments",
        estimated_monthly_cost=272.66, monthly_cost_if_stopped=23.0,
        monthly_saving_if_stopped=58.25, billing_while_stopped=False,
        tags={"Name": "checkout-prod-db", "Project": "checkout",
              "Environment": "prod", "Owner": "team-payments"},
    ),
]

CACHES = [
    CloudResource(
        resource_id="payments-dev-redis", resource_type="cache", region="us-east-1",
        name="payments-dev-redis", state="available",
        instance_type="cache.t3.micro", engine="redis", node_count=2,
        launch_time="2026-05-02T12:15:00+00:00",
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=24.82, billing_while_stopped=True,
        tags={"Name": "payments-dev-redis", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
]

SNAPSHOTS = [
    CloudResource(
        # Safe to delete: nothing references it and its volume is long gone.
        resource_id="snap-0stale4321", resource_type="snapshot", region="us-east-1",
        name="payments-poc-pre-migration", state="completed", size_gb=100,
        attached_to="vol-0deleted99",
        launch_time="2026-03-18T04:00:00+00:00",
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=5.0, billing_while_stopped=True,
        tags={"Name": "payments-poc-pre-migration", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
    CloudResource(
        # Backs an AMI. AWS refuses the delete until the image is deregistered,
        # which is exactly the ordering problem the planner exists to solve.
        resource_id="snap-0golden0001", resource_type="snapshot", region="us-east-1",
        name="payments-base-image", state="completed", size_gb=40,
        attached_to="vol-0golden77", image_ids=["ami-0base12345"],
        launch_time="2026-02-02T06:30:00+00:00",
        project="payments", environment="dev", owner="hayden",
        estimated_monthly_cost=2.0, billing_while_stopped=True,
        tags={"Name": "payments-base-image", "Project": "payments",
              "Environment": "dev", "Owner": "hayden"},
    ),
]

# The NAT gateway holds its own Elastic IP, which must be released after the
# gateway is deleted, never before.
ADDRESSES.append(
    CloudResource(
        resource_id="eipalloc-0nat7788", resource_type="eip", region="us-east-1",
        state="associated", public_ip="52.20.145.3", attached_to="nat-0d1e2f3a4b5c6",
        estimated_monthly_cost=3.65, billing_while_stopped=True,
        tags={"Name": "payments-dev-nat-ip", "AssociationId": ""},
    )
)

USAGE = {
    "i-0abc123def456789": dict(avg_cpu_percent=0.4, max_cpu_percent=1.1, idle_days=41,
                               network_in_bytes=2048.0, network_out_bytes=1024.0),
    "i-0999prod888": dict(avg_cpu_percent=34.7, max_cpu_percent=81.2, idle_days=0,
                          network_in_bytes=9.2e9, network_out_bytes=7.7e9),
}

NAT_USAGE = {
    "nat-0d1e2f3a4b5c6": dict(
        metric_source="NATGateway/BytesOutToDestination",
        bytes_processed=0.0, idle_days=58,
    ),
}

ELB_USAGE = {
    LOAD_BALANCERS[0].resource_id: dict(
        metric_source="ApplicationELB/RequestCount", request_count=0.0, idle_days=58
    ),
}

RDS_USAGE = {
    "payments-dev-db": dict(
        metric_source="RDS/DatabaseConnections",
        avg_cpu_percent=0.0, connection_count=0.0, idle_days=58,
    ),
    "checkout-prod-db": dict(
        metric_source="RDS/DatabaseConnections",
        avg_cpu_percent=28.4, connection_count=64.0, idle_days=0,
    ),
}

CACHE_USAGE = {
    "payments-dev-redis": dict(
        metric_source="ElastiCache/CurrConnections",
        connection_count=0.0, bytes_processed=0.0, idle_days=58,
    ),
}

HEALTHY_TARGETS = {LOAD_BALANCERS[0].target_group_ids[0]: 0}

# Matches the §5.2 demo narrative: "last commit 6 weeks ago, branch deleted, PR merged."
GITHUB = {
    "wkxcass/cloudcleaner-demo-payments": dict(
        latest_commit_at="2026-07-20T10:00:00+00:00",
        pr_number=42, pr_status="merged", branch="feature/payments-poc",
        branch_exists=False, last_workflow_run_at="2026-07-20T10:30:00+00:00",
        scheduled_workflow_exists=False,
    ),
}


def list_ec2_instances():
    return [i.model_copy(deep=True) for i in INSTANCES]


def list_volumes(only_unattached: bool = False):
    vols = [v.model_copy(deep=True) for v in VOLUMES]
    return [v for v in vols if v.attached_to is None] if only_unattached else vols


def list_elastic_ips():
    return [a.model_copy(deep=True) for a in ADDRESSES]


def list_nat_gateways():
    return [n.model_copy(deep=True) for n in NAT_GATEWAYS]


def list_load_balancers():
    return [lb.model_copy(deep=True) for lb in LOAD_BALANCERS]


def list_rds_instances():
    return [d.model_copy(deep=True) for d in DATABASES]


def list_cache_clusters():
    return [c.model_copy(deep=True) for c in CACHES]


def list_snapshots(owned_by_self: bool = True):
    return [s.model_copy(deep=True) for s in SNAPSHOTS]


def healthy_target_count(target_group_arns: list[str]) -> int:
    return sum(HEALTHY_TARGETS.get(arn, 0) for arn in target_group_arns)


def get_nat_usage_evidence(nat_id: str, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **NAT_USAGE.get(nat_id, {}))


def get_elb_usage_evidence(arn: str, lb_type: str | None = None, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **ELB_USAGE.get(arn, {}))


def get_rds_usage_evidence(db_id: str, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **RDS_USAGE.get(db_id, {}))


def get_cache_usage_evidence(cluster_id: str, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **CACHE_USAGE.get(cluster_id, {}))


def get_ec2_usage_evidence(instance_id: str, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **USAGE.get(instance_id, {}))


def get_github_evidence(repo: str | None = None):
    from cloudcleaner.schemas import GitHubEvidence
    if not repo:
        return GitHubEvidence()
    return GitHubEvidence(repo=repo, **GITHUB.get(repo, {}))
