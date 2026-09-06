"""The boto3 read paths, driven by AWS-shaped responses.

These parsers never run in the fixture demo, so without this file they would
ship unexercised. Every response shape below matches the real describe_* output.
"""

from datetime import datetime, timezone

import pytest

from cloudcleaner.tools.aws import caches, databases, gateways, loadbalancers, volumes

CREATED = datetime(2026, 5, 2, 11, 20, tzinfo=timezone.utc)


class FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        return self._pages


class FakeClient:
    """Stands in for a boto3 client: paginators plus direct calls."""

    def __init__(self, pages=None, **responses):
        self._pages = pages or {}
        self._responses = responses
        self.calls = []

    def get_paginator(self, name):
        return FakePaginator(self._pages.get(name, []))

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            value = self._responses.get(name, {})
            return value(**kwargs) if callable(value) else value
        return call


# --- NAT gateways --------------------------------------------------------------


def _nat_client(state="available"):
    return FakeClient(
        pages={"describe_nat_gateways": [{"NatGateways": [{
            "NatGatewayId": "nat-01234", "State": state,
            "VpcId": "vpc-1", "SubnetId": "subnet-1", "CreateTime": CREATED,
            "NatGatewayAddresses": [
                {"AllocationId": "eipalloc-9", "PublicIp": "52.1.2.3"}
            ],
            "Tags": [{"Key": "Name", "Value": "egress"}, {"Key": "Owner", "Value": "hayden"}],
        }]}]},
        describe_route_tables={"RouteTables": [{"RouteTableId": "rtb-1"}]},
    )


def test_nat_gateway_is_parsed_with_its_address_and_routes(monkeypatch):
    monkeypatch.setattr(gateways, "get_ec2_client", _nat_client)
    [nat] = gateways.list_nat_gateways()

    assert nat.resource_id == "nat-01234"
    assert nat.resource_type == "nat"
    assert nat.address_ids == ["eipalloc-9"]
    assert nat.route_table_ids == ["rtb-1"]
    assert nat.owner == "hayden"
    assert nat.billing_while_stopped is True
    assert nat.estimated_monthly_cost == pytest.approx(32.85, abs=0.01)


@pytest.mark.parametrize("state", ["deleted", "deleting"])
def test_gateways_already_going_away_are_skipped(monkeypatch, state):
    monkeypatch.setattr(gateways, "get_ec2_client", lambda: _nat_client(state))

    assert gateways.list_nat_gateways() == []


def test_route_lookup_filters_on_the_gateway_itself(monkeypatch):
    client = _nat_client()
    monkeypatch.setattr(gateways, "get_ec2_client", lambda: client)
    gateways.list_nat_gateways()

    [(name, kwargs)] = [c for c in client.calls if c[0] == "describe_route_tables"]
    assert kwargs["Filters"] == [
        {"Name": "route.nat-gateway-id", "Values": ["nat-01234"]}
    ]


# --- load balancers ------------------------------------------------------------

LB_ARN = "arn:aws:elasticloadbalancing:us-east-1:1:loadbalancer/app/web/abc123"


def _elb_client():
    return FakeClient(
        pages={"describe_load_balancers": [{"LoadBalancers": [{
            "LoadBalancerArn": LB_ARN, "LoadBalancerName": "web", "Type": "application",
            "State": {"Code": "active"}, "VpcId": "vpc-1", "CreatedTime": CREATED,
        }]}]},
        describe_tags={"TagDescriptions": [{"Tags": [{"Key": "Owner", "Value": "hayden"}]}]},
        describe_listeners={"Listeners": [{"ListenerArn": "arn:listener/1"}]},
        describe_target_groups={"TargetGroups": [{"TargetGroupArn": "arn:tg/1"}]},
    )


def test_load_balancer_is_parsed_with_listeners_and_target_groups(monkeypatch):
    monkeypatch.setattr(loadbalancers, "get_elbv2_client", _elb_client)
    [lb] = loadbalancers.list_load_balancers()

    assert lb.resource_id == LB_ARN
    assert lb.instance_type == "application"
    assert lb.listener_ids == ["arn:listener/1"]
    assert lb.target_group_ids == ["arn:tg/1"]
    assert lb.estimated_monthly_cost == pytest.approx(16.43, abs=0.01)


def test_a_balancer_whose_tags_cannot_be_read_is_still_listed(monkeypatch):
    """Missing elasticloadbalancing:DescribeTags must not hide the cost."""
    client = _elb_client()
    client._responses["describe_tags"] = lambda **kw: (_ for _ in ()).throw(
        RuntimeError("AccessDenied")
    )
    monkeypatch.setattr(loadbalancers, "get_elbv2_client", lambda: client)
    [lb] = loadbalancers.list_load_balancers()

    assert lb.tags == {}
    assert lb.estimated_monthly_cost > 0


def test_healthy_targets_are_counted_across_groups(monkeypatch):
    client = FakeClient(describe_target_health={"TargetHealthDescriptions": [
        {"TargetHealth": {"State": "healthy"}},
        {"TargetHealth": {"State": "unused"}},
    ]})
    monkeypatch.setattr(loadbalancers, "get_elbv2_client", lambda: client)

    assert loadbalancers.healthy_target_count(["tg-1", "tg-2"]) == 2


# --- RDS -----------------------------------------------------------------------


def _rds_client(status="stopped", **overrides):
    db = {
        "DBInstanceIdentifier": "payments-db", "DBInstanceStatus": status,
        "DBInstanceClass": "db.t3.small", "Engine": "postgres",
        "AllocatedStorage": 20, "StorageType": "gp2", "MultiAZ": False,
        "DeletionProtection": False, "InstanceCreateTime": CREATED,
        "DBSubnetGroup": {"VpcId": "vpc-1"},
        "TagList": [{"Key": "Owner", "Value": "hayden"}],
    }
    db.update(overrides)
    return FakeClient(pages={"describe_db_instances": [{"DBInstances": [db]}]})


def test_stopped_database_is_reported_as_still_billing(monkeypatch):
    monkeypatch.setattr(databases, "get_rds_client", _rds_client)
    [db] = databases.list_rds_instances()

    assert db.state == "stopped"
    assert db.billing_while_stopped is True
    assert db.estimated_monthly_cost == pytest.approx(2.30, abs=0.01)
    assert db.monthly_saving_if_stopped == 0.0, "it is already stopped; nothing left to save"


def test_running_database_is_not_billing_while_stopped(monkeypatch):
    monkeypatch.setattr(databases, "get_rds_client", lambda: _rds_client("available"))
    [db] = databases.list_rds_instances()

    assert db.billing_while_stopped is False
    assert db.estimated_monthly_cost > db.monthly_cost_if_stopped


def test_deletion_protection_is_carried_into_the_plan(monkeypatch):
    monkeypatch.setattr(
        databases, "get_rds_client", lambda: _rds_client("available", DeletionProtection=True)
    )
    [db] = databases.list_rds_instances()

    assert db.deletion_protection is True


# --- ElastiCache ---------------------------------------------------------------


def _cache_client(nodes=2):
    return FakeClient(
        pages={"describe_cache_clusters": [{"CacheClusters": [{
            "CacheClusterId": "sessions", "CacheClusterStatus": "available",
            "CacheNodeType": "cache.t3.micro", "Engine": "redis",
            "NumCacheNodes": nodes, "CacheClusterCreateTime": CREATED,
            "ARN": "arn:aws:elasticache:us-east-1:1:cluster:sessions",
        }]}]},
        list_tags_for_resource={"TagList": [{"Key": "Owner", "Value": "hayden"}]},
    )


def test_cache_cost_reflects_the_node_count(monkeypatch):
    monkeypatch.setattr(caches, "get_elasticache_client", _cache_client)
    [cluster] = caches.list_cache_clusters()

    assert cluster.node_count == 2
    assert cluster.engine == "redis"
    assert cluster.estimated_monthly_cost == pytest.approx(24.82, abs=0.02)
    assert cluster.billing_while_stopped is True, "ElastiCache has no stopped state"


def test_a_cache_whose_tags_cannot_be_read_is_still_listed(monkeypatch):
    client = _cache_client()
    client._responses["list_tags_for_resource"] = lambda **kw: (_ for _ in ()).throw(
        RuntimeError("AccessDenied")
    )
    monkeypatch.setattr(caches, "get_elasticache_client", lambda: client)
    [cluster] = caches.list_cache_clusters()

    assert cluster.tags == {}


# --- snapshots and their AMIs --------------------------------------------------


def _snapshot_client(images=None):
    return FakeClient(
        pages={"describe_snapshots": [{"Snapshots": [
            {"SnapshotId": "snap-1", "State": "completed", "VolumeSize": 100,
             "VolumeId": "vol-1", "StartTime": CREATED, "Tags": []},
            {"SnapshotId": "snap-2", "State": "completed", "VolumeSize": 40,
             "VolumeId": "vol-2", "StartTime": CREATED, "Tags": []},
        ]}]},
        describe_images={"Images": images if images is not None else []},
    )


def test_snapshots_are_linked_to_the_amis_built_on_them(monkeypatch):
    images = [{"ImageId": "ami-1", "BlockDeviceMappings": [
        {"Ebs": {"SnapshotId": "snap-2"}}, {"VirtualName": "ephemeral0"},
    ]}]
    monkeypatch.setattr(volumes, "get_ec2_client", lambda: _snapshot_client(images))
    by_id = {s.resource_id: s for s in volumes.list_snapshots()}

    assert by_id["snap-2"].image_ids == ["ami-1"]
    assert by_id["snap-1"].image_ids == []


def test_snapshots_still_list_when_images_cannot_be_read(monkeypatch):
    """Without ec2:DescribeImages we lose the AMI edge, not the whole listing."""
    client = _snapshot_client()
    client._responses["describe_images"] = lambda **kw: (_ for _ in ()).throw(
        RuntimeError("AccessDenied")
    )
    monkeypatch.setattr(volumes, "get_ec2_client", lambda: client)
    snapshots = volumes.list_snapshots()

    assert len(snapshots) == 2
    assert all(s.image_ids == [] for s in snapshots)
