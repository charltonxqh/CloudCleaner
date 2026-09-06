"""The five resource types beyond EC2/EBS/EIP: cost, idle signal, teardown order.

Each type is judged by the metric AWS actually publishes for it, and each has a
teardown chain that AWS would reject if run in any other order.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cloudcleaner.fixtures import demo
from cloudcleaner.graph.nodes.detect import _wasted_monthly, detect_node
from cloudcleaner.policy.dependencies import IRREVERSIBLE, resolve
from cloudcleaner.policy.risk import classify_severity, rules_only_verdict
from cloudcleaner.schemas import AWSEvidence, CloudResource
from cloudcleaner.tools.aws.actions import ACTIONS
from cloudcleaner.tools.aws.cost import (
    elasticache_cost,
    load_balancer_cost,
    nat_gateway_cost,
    rds_cost,
    rds_monthly_saving_if_stopped,
)
from cloudcleaner.tools.provider import get_usage_evidence

NEW_TYPES = ("nat", "elb", "rds", "cache", "snapshot")


def _order_of(steps):
    return {(s.action, s.resource_id): s.order for s in steps}


def _before(steps, first, second):
    """True when every step matching `first` runs before every step matching `second`."""
    orders = _order_of(steps)
    firsts = [o for (a, _), o in orders.items() if a == first]
    seconds = [o for (a, _), o in orders.items() if a == second]
    assert firsts and seconds, f"expected both {first} and {second} in the plan"
    return max(firsts) < min(seconds)


# --- cost ---------------------------------------------------------------------


def test_nat_gateway_bills_while_completely_idle():
    """There is no stopped state. An idle gateway costs the same as a busy one."""
    assert nat_gateway_cost(0) == pytest.approx(32.85, abs=0.01)
    assert nat_gateway_cost(100) > nat_gateway_cost(0)


def test_load_balancer_base_rate_is_charged_with_no_traffic():
    assert load_balancer_cost("application") == pytest.approx(16.43, abs=0.01)
    assert load_balancer_cost("gateway") < load_balancer_cost("application")
    assert load_balancer_cost(None) == load_balancer_cost("application")


def test_stopped_rds_still_bills_for_storage():
    """The EC2 trap one level worse: stopping releases compute only."""
    running, running_residual = rds_cost("available", "db.t3.small", 20, "gp2")
    stopped, stopped_residual = rds_cost("stopped", "db.t3.small", 20, "gp2")

    assert running > stopped
    assert running_residual is False
    assert stopped_residual is True, "a stopped database is not free"
    assert stopped == pytest.approx(2.30, abs=0.01)


def test_rds_stop_saving_is_capped_at_seven_days():
    """AWS force-starts a stopped instance after 7 days, so a month is not on offer."""
    saving = rds_monthly_saving_if_stopped("available", "db.t3.small", 20, "gp2")
    full_month, _ = rds_cost("available", "db.t3.small", 20, "gp2")

    assert 0 < saving < full_month * 0.25


def test_multi_az_rds_costs_double_the_compute():
    single, _ = rds_cost("available", "db.m5.large", 100, "gp2")
    multi, _ = rds_cost("available", "db.m5.large", 100, "gp2", multi_az=True)

    storage = single - multi / 2
    assert multi > single
    assert storage > 0


def test_elasticache_scales_with_node_count():
    assert elasticache_cost("cache.t3.micro", 2) == pytest.approx(
        elasticache_cost("cache.t3.micro", 1) * 2, abs=0.01
    )


# --- teardown ordering --------------------------------------------------------


def test_nat_routes_come_out_before_the_gateway_and_the_address_last():
    """AWS rejects delete_nat_gateway while a route points at it, and the
    address cannot be released until the gateway holding it is gone."""
    steps = resolve(demo.NAT_GATEWAYS[0], [], demo.ADDRESSES)

    assert _before(steps, "delete_route", "delete_nat_gateway")
    assert _before(steps, "delete_nat_gateway", "release_address")


def test_nat_plan_covers_every_route_table():
    nat = demo.NAT_GATEWAYS[0]
    steps = resolve(nat, [], demo.ADDRESSES)
    removed = {s.resource_id for s in steps if s.action == "delete_route"}

    assert removed == set(nat.route_table_ids)


def test_load_balancer_listener_then_balancer_then_target_group():
    steps = resolve(demo.LOAD_BALANCERS[0], [], [])

    assert _before(steps, "delete_listener", "delete_load_balancer")
    assert _before(steps, "delete_load_balancer", "delete_target_group")


def test_rds_takes_a_snapshot_before_the_irreversible_delete():
    steps = resolve(demo.DATABASES[0], [], [])

    assert _before(steps, "snapshot_database", "delete_db_instance")


def test_rds_deletion_protection_is_lifted_first():
    protected = demo.DATABASES[0].model_copy(update={"deletion_protection": True})
    steps = resolve(protected, [], [])

    assert _before(steps, "disable_deletion_protection", "delete_db_instance")


def test_redis_is_snapshotted_but_memcached_cannot_be():
    redis = resolve(demo.CACHES[0], [], [])
    memcached = resolve(demo.CACHES[0].model_copy(update={"engine": "memcached"}), [], [])

    assert any(s.action == "snapshot_cache" for s in redis)
    assert not any(s.action == "snapshot_cache" for s in memcached), (
        "memcached has no snapshot API, so no restore point may be promised"
    )
    assert any(s.action == "delete_cache_cluster" for s in memcached)


def test_snapshot_backing_an_ami_deregisters_the_image_first():
    golden = demo.SNAPSHOTS[1]
    assert golden.image_ids

    steps = resolve(golden, [], [])
    assert _before(steps, "deregister_image", "delete_snapshot")


def test_unreferenced_snapshot_needs_no_preamble():
    steps = resolve(demo.SNAPSHOTS[0], [], [])

    assert [s.action for s in steps] == ["delete_snapshot"]


@pytest.mark.parametrize("root", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0],
    demo.DATABASES[0], demo.CACHES[0], demo.SNAPSHOTS[1],
])
def test_every_step_runs_after_everything_it_depends_on(root):
    steps = resolve(root, [], demo.ADDRESSES)
    orders = _order_of(steps)

    for step in steps:
        for dep in step.depends_on:
            action, _, rid = dep.partition(":")
            if (action, rid) in orders:
                assert orders[(action, rid)] < step.order, f"{dep} must precede {step.action}"


@pytest.mark.parametrize("root", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0],
    demo.DATABASES[0], demo.CACHES[0], demo.SNAPSHOTS[1],
])
def test_orders_are_a_dense_sequence_from_one(root):
    steps = resolve(root, [], demo.ADDRESSES)

    assert sorted(s.order for s in steps) == list(range(1, len(steps) + 1))


@pytest.mark.parametrize("root", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0],
    demo.DATABASES[0], demo.CACHES[0], demo.SNAPSHOTS[1],
])
def test_every_planned_action_is_executable(root):
    """A plan that names an action no executor implements is a plan that stalls."""
    for step in resolve(root, [], demo.ADDRESSES):
        assert step.action in ACTIONS, f"{step.action} has no executor"


@pytest.mark.parametrize("root", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0],
    demo.DATABASES[0], demo.CACHES[0], demo.SNAPSHOTS[1],
])
def test_irreversible_steps_are_flagged_as_such(root):
    for step in resolve(root, [], demo.ADDRESSES):
        assert step.reversible == (step.action not in IRREVERSIBLE), (
            f"{step.action} is mislabelled"
        )


@pytest.mark.parametrize("root", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0], demo.DATABASES[0], demo.CACHES[0],
])
def test_the_saving_is_claimed_exactly_once_per_plan(root):
    """Double-counting a saving across steps would inflate the headline figure."""
    steps = resolve(root, [], [])
    claiming = [s for s in steps if s.monthly_saving == root.estimated_monthly_cost]

    assert len(claiming) == 1


# --- idle signals and verdicts -------------------------------------------------


EXPECTED_METRIC = {
    "nat": "NATGateway/BytesOutToDestination",
    "elb": "ApplicationELB/RequestCount",
    "rds": "RDS/DatabaseConnections",
    "cache": "ElastiCache/CurrConnections",
}


@pytest.mark.parametrize("resource", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0],
    demo.DATABASES[0], demo.DATABASES[1], demo.CACHES[0],
])
def test_each_type_reports_the_metric_aws_publishes_for_it(resource):
    evidence = get_usage_evidence(resource)

    assert evidence.metric_source == EXPECTED_METRIC[resource.resource_type]


def test_cpu_is_never_the_signal_for_a_type_that_has_no_cpu():
    """A NAT gateway, a balancer and a cache emit no CPU. Reading zero CPU as
    'idle' would be inferring use from a metric that does not exist."""
    for resource in (demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0], demo.CACHES[0]):
        assert get_usage_evidence(resource).avg_cpu_percent is None


def test_types_without_any_metrics_report_none_rather_than_zero():
    """Zero would read as 'measured and idle'. None reads as 'not measurable'."""
    for resource in (demo.SNAPSHOTS[0], demo.VOLUMES[1], demo.ADDRESSES[1]):
        evidence = get_usage_evidence(resource)
        assert evidence.avg_cpu_percent is None
        assert evidence.connection_count is None
        assert evidence.request_count is None


def test_nat_with_no_traffic_is_retired_not_stopped():
    """A NAT gateway cannot be stopped, so 'stop' would be an impossible verdict."""
    rec = rules_only_verdict(demo.NAT_GATEWAYS[0], get_usage_evidence(demo.NAT_GATEWAYS[0]))

    assert rec.action == "retire"
    assert "cannot be stopped" in rec.reason


def test_nat_carrying_traffic_is_kept():
    busy = AWSEvidence(bytes_processed=9.4e9, idle_days=0)
    rec = rules_only_verdict(demo.NAT_GATEWAYS[0], busy)

    assert rec.action == "keep"


def test_nat_without_metrics_is_not_guessed_at():
    rec = rules_only_verdict(demo.NAT_GATEWAYS[0], AWSEvidence())

    assert rec.action == "investigate_more"


def test_idle_load_balancer_is_retired():
    rec = rules_only_verdict(demo.LOAD_BALANCERS[0], get_usage_evidence(demo.LOAD_BALANCERS[0]))

    assert rec.action == "retire"


def test_load_balancer_serving_requests_is_kept():
    busy = AWSEvidence(request_count=142_000, idle_days=0)
    rec = rules_only_verdict(demo.LOAD_BALANCERS[0], busy)

    assert rec.action == "keep"


def test_stopped_database_is_retired_because_stopping_solved_nothing():
    db = demo.DATABASES[0]
    rec = rules_only_verdict(db, get_usage_evidence(db))

    assert rec.action == "retire"
    assert "7 days" in rec.reason, "the auto-restart is the whole point"


def test_busy_production_database_is_kept():
    db = demo.DATABASES[1]
    rec = rules_only_verdict(db, get_usage_evidence(db))

    assert rec.action == "keep"


def test_idle_cache_is_retired():
    rec = rules_only_verdict(demo.CACHES[0], get_usage_evidence(demo.CACHES[0]))

    assert rec.action == "retire"


def test_snapshot_backing_an_ami_is_held_for_investigation():
    rec = rules_only_verdict(demo.SNAPSHOTS[1], AWSEvidence())

    assert rec.action == "investigate_more"
    assert "ami-0base12345" in rec.reason


def test_old_unreferenced_snapshot_is_retired():
    rec = rules_only_verdict(demo.SNAPSHOTS[0], AWSEvidence())

    assert rec.action == "retire"


@pytest.mark.parametrize("resource", [
    demo.NAT_GATEWAYS[0], demo.LOAD_BALANCERS[0], demo.DATABASES[0], demo.CACHES[0],
])
def test_idle_unpausable_resources_are_high_severity(resource):
    assert classify_severity(resource, get_usage_evidence(resource)) == "high"


# --- detection over the whole account -----------------------------------------


def test_scan_finds_all_eight_resource_types():
    scan = detect_node({})
    found = {r.resource_type for r in scan["inventory"] + scan["orphans"]}

    assert found == {"ec2", "ebs", "eip", "snapshot", "nat", "elb", "rds", "cache"}


def test_production_resources_contribute_no_waste():
    """A busy prod database is expensive, not wasteful. Ranking must not confuse them."""
    scan = detect_node({})
    prod = [r for r in scan["inventory"] if (r.environment or "") == "prod"]

    assert prod, "fixture should contain production resources"
    for resource in prod:
        assert _wasted_monthly(resource) == 0.0
        assert (resource.estimated_monthly_cost or 0) > 0


def test_the_costliest_waste_is_selected_first():
    scan = detect_node({})
    pool = scan["inventory"] + scan["orphans"]
    worst = max(pool, key=_wasted_monthly)

    assert scan["resource"].resource_id == worst.resource_id
    assert scan["resource"].resource_type == "nat"


def test_a_gateways_address_is_not_also_counted_as_an_orphan():
    """It is part of the gateway's teardown; counting it twice inflates the total."""
    scan = detect_node({})
    held = {a for g in demo.NAT_GATEWAYS for a in g.address_ids}
    orphan_ids = {r.resource_id for r in scan["orphans"]}

    assert not (held & orphan_ids)


def test_a_failing_service_does_not_blank_the_scan(monkeypatch):
    """One missing IAM permission must not hide the rest of the account."""
    def boom():
        raise RuntimeError("AccessDenied: elasticache:DescribeCacheClusters")

    monkeypatch.setattr("cloudcleaner.graph.nodes.detect.list_cache_clusters", boom)
    scan = detect_node({})
    found = {r.resource_type for r in scan["inventory"] + scan["orphans"]}

    assert "cache" not in found
    assert {"ec2", "nat", "elb", "rds"} <= found


def test_every_discovered_resource_can_be_planned():
    """No type may be discoverable but unplannable - that would be a dead end in the UI."""
    scan = detect_node({})

    for resource in scan["inventory"] + scan["orphans"]:
        steps = resolve(resource, scan["volumes"], scan["addresses"])
        assert isinstance(steps, list)


# --- properties ----------------------------------------------------------------

costs = st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False)


@given(cost=costs, idle=st.integers(min_value=0, max_value=400))
@settings(max_examples=50, deadline=None)
def test_waste_never_exceeds_total_cost(cost, idle):
    for resource_type in NEW_TYPES:
        resource = CloudResource(
            resource_id="r-1", resource_type=resource_type, region="us-east-1",
            state="available", idle_days=idle, estimated_monthly_cost=cost,
            billing_while_stopped=True,
        )
        assert 0 <= _wasted_monthly(resource) <= cost + 1e-9


@given(
    storage=st.integers(min_value=0, max_value=4000),
    instance_class=st.sampled_from(["db.t3.micro", "db.t3.small", "db.m5.large", "db.unknown"]),
)
@settings(max_examples=50, deadline=None)
def test_stopping_a_database_never_costs_more_than_running_it(storage, instance_class):
    running, _ = rds_cost("available", instance_class, storage, "gp2")
    stopped, _ = rds_cost("stopped", instance_class, storage, "gp2")

    assert stopped <= running


@given(storage=st.integers(min_value=1, max_value=4000))
@settings(max_examples=50, deadline=None)
def test_a_stopped_database_with_storage_always_still_bills(storage):
    _, residual = rds_cost("stopped", "db.t3.small", storage, "gp2")

    assert residual is True
