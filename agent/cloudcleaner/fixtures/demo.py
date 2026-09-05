"""Offline demo stack. Shapes match real describe_* responses so the graph cannot tell."""

from cloudcleaner.schemas import CloudResource

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

USAGE = {
    "i-0abc123def456789": dict(avg_cpu_percent=0.4, max_cpu_percent=1.1, idle_days=41,
                               network_in_bytes=2048.0, network_out_bytes=1024.0),
    "i-0999prod888": dict(avg_cpu_percent=34.7, max_cpu_percent=81.2, idle_days=0,
                          network_in_bytes=9.2e9, network_out_bytes=7.7e9),
}


def list_ec2_instances():
    return [i.model_copy(deep=True) for i in INSTANCES]


def list_volumes(only_unattached: bool = False):
    vols = [v.model_copy(deep=True) for v in VOLUMES]
    return [v for v in vols if v.attached_to is None] if only_unattached else vols


def list_elastic_ips():
    return [a.model_copy(deep=True) for a in ADDRESSES]


def get_ec2_usage_evidence(instance_id: str, days: int = 7):
    from cloudcleaner.schemas import AWSEvidence
    return AWSEvidence(metric_window_days=days, **USAGE.get(instance_id, {}))
