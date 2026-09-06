"""Which CloudWatch series each type is actually queried against.

This matters more than it looks. A wrong namespace or dimension returns no
datapoints rather than an error, and "no datapoints" would otherwise read as
"idle" - so a typo here becomes a confident recommendation to delete something
that is in use. Every query is asserted exactly.
"""

from datetime import datetime, timedelta, timezone

import pytest

from cloudcleaner.tools.aws import metrics

NOW = datetime.now(timezone.utc)


class RecordingCloudWatch:
    def __init__(self, datapoints=None):
        self.queries = []
        self._datapoints = datapoints or []

    def get_metric_statistics(self, **kwargs):
        self.queries.append(kwargs)
        return {"Datapoints": self._datapoints}


@pytest.fixture
def cw(monkeypatch):
    client = RecordingCloudWatch()
    monkeypatch.setattr(metrics, "get_cloudwatch_client", lambda: client)
    return client


def _query_for(client, metric_name):
    matches = [q for q in client.queries if q["MetricName"] == metric_name]
    assert matches, f"{metric_name} was never queried. Asked for: " + ", ".join(
        sorted({q["MetricName"] for q in client.queries})
    )
    return matches[0]


EXPECTED = [
    # collector,                     metric,                   namespace,             dimension
    ("nat", "BytesOutToDestination", "AWS/NATGateway", "NatGatewayId"),
    ("rds", "DatabaseConnections", "AWS/RDS", "DBInstanceIdentifier"),
    ("cache", "CurrConnections", "AWS/ElastiCache", "CacheClusterId"),
]


@pytest.mark.parametrize("kind,metric,namespace,dimension", EXPECTED)
def test_each_type_is_queried_against_its_own_series(cw, kind, metric, namespace, dimension):
    getattr(metrics, f"get_{kind}_usage_evidence")("resource-1")
    query = _query_for(cw, metric)

    assert query["Namespace"] == namespace
    assert query["Dimensions"] == [{"Name": dimension, "Value": "resource-1"}]


def test_application_balancers_use_request_count(cw):
    metrics.get_elb_usage_evidence("arn:aws:elb:::loadbalancer/app/web/abc", "application")
    query = _query_for(cw, "RequestCount")

    assert query["Namespace"] == "AWS/ApplicationELB"


def test_network_balancers_use_flow_count_instead(cw):
    """An NLB publishes no RequestCount at all, so asking for it would find nothing."""
    metrics.get_elb_usage_evidence("arn:aws:elb:::loadbalancer/net/web/abc", "network")
    query = _query_for(cw, "ActiveFlowCount")

    assert query["Namespace"] == "AWS/NetworkELB"


def test_balancer_dimension_is_the_arn_suffix_not_the_whole_arn(cw):
    """CloudWatch keys balancers by 'app/name/id'. The full arn matches nothing."""
    metrics.get_elb_usage_evidence(
        "arn:aws:elasticloadbalancing:us-east-1:1:loadbalancer/app/web/abc123", "application"
    )
    query = _query_for(cw, "RequestCount")

    assert query["Dimensions"] == [{"Name": "LoadBalancer", "Value": "app/web/abc123"}]


def test_a_bare_dimension_is_passed_through_unchanged(cw):
    metrics.get_elb_usage_evidence("app/web/abc123", "application")
    query = _query_for(cw, "RequestCount")

    assert query["Dimensions"] == [{"Name": "LoadBalancer", "Value": "app/web/abc123"}]


def test_ec2_still_reads_cpu_from_its_own_namespace(cw):
    metrics.get_ec2_usage_evidence("i-1")
    query = _query_for(cw, "CPUUtilization")

    assert query["Namespace"] == "AWS/EC2"
    assert query["Dimensions"] == [{"Name": "InstanceId", "Value": "i-1"}]


def test_no_datapoints_reports_none_rather_than_zero(cw):
    """Zero would mean 'measured no traffic'. None means 'nothing was measured'."""
    evidence = metrics.get_nat_usage_evidence("nat-1")

    assert evidence.bytes_processed is None
    assert evidence.idle_days is None


def test_idle_days_counts_back_to_the_last_active_bucket(monkeypatch):
    client = RecordingCloudWatch([
        {"Timestamp": NOW - timedelta(days=40), "Maximum": 5_000_000.0, "Sum": 5_000_000.0},
        {"Timestamp": NOW - timedelta(days=12), "Maximum": 0.0, "Sum": 0.0},
    ])
    monkeypatch.setattr(metrics, "get_cloudwatch_client", lambda: client)

    assert metrics.get_nat_usage_evidence("nat-1").idle_days == 40


def test_a_series_that_was_never_active_reports_the_full_lookback(monkeypatch):
    client = RecordingCloudWatch([
        {"Timestamp": NOW - timedelta(days=d), "Maximum": 0.0, "Sum": 0.0} for d in (1, 30, 60)
    ])
    monkeypatch.setattr(metrics, "get_cloudwatch_client", lambda: client)

    assert metrics.get_nat_usage_evidence("nat-1").idle_days == metrics.MAX_IDLE_LOOKBACK_DAYS


def test_idle_days_are_measured_in_daily_buckets(cw):
    """Hourly buckets over 90 days would blow past the CloudWatch datapoint cap."""
    metrics.get_nat_usage_evidence("nat-1")
    daily = [q for q in cw.queries if q["Period"] == 86400]

    assert daily, "the idle-days lookback must use daily periods"
    assert all(q["Namespace"] == "AWS/NATGateway" for q in daily)


def test_every_collector_names_the_source_it_used(cw):
    for kind in ("nat", "rds", "cache"):
        evidence = getattr(metrics, f"get_{kind}_usage_evidence")("resource-1")
        assert evidence.metric_source, f"{kind} did not record its metric source"

    assert metrics.get_elb_usage_evidence("app/web/abc", "application").metric_source
