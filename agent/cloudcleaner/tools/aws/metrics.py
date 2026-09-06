from datetime import datetime, timedelta, timezone

from cloudcleaner.config import METRIC_WINDOW_DAYS
from cloudcleaner.schemas import AWSEvidence
from cloudcleaner.tools.aws.client import get_cloudwatch_client

MAX_IDLE_LOOKBACK_DAYS = 90


def _window(days: int):
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def _points(
    namespace: str,
    dimension: str,
    value: str,
    metric: str,
    stat: str,
    days: int,
    period: int = 3600,
):
    start, end = _window(days)
    resp = get_cloudwatch_client().get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=[{"Name": dimension, "Value": value}],
        StartTime=start,
        EndTime=end,
        Period=period,
        Statistics=[stat],
    )
    return resp["Datapoints"]


def _stat(instance_id: str, metric: str, stat: str, days: int, period: int = 3600):
    return _points("AWS/EC2", "InstanceId", instance_id, metric, stat, days, period)


def _sum(namespace, dimension, value, metric, days) -> float | None:
    points = _points(namespace, dimension, value, metric, "Sum", days)
    return sum(p["Sum"] for p in points) if points else None


def _avg(namespace, dimension, value, metric, days) -> float | None:
    points = _points(namespace, dimension, value, metric, "Average", days)
    return round(sum(p["Average"] for p in points) / len(points), 3) if points else None


def _peak(namespace, dimension, value, metric, days) -> float | None:
    points = _points(namespace, dimension, value, metric, "Maximum", days)
    return max(p["Maximum"] for p in points) if points else None


def _days_since_active(
    namespace: str, dimension: str, value: str, metric: str, threshold: float = 0.0
) -> int | None:
    """Daily buckets over the lookback window; days since the last one above threshold."""
    points = _points(
        namespace, dimension, value, metric, "Maximum", MAX_IDLE_LOOKBACK_DAYS, period=86400
    )
    if not points:
        return None

    active = [p for p in points if p["Maximum"] > threshold]
    if not active:
        return MAX_IDLE_LOOKBACK_DAYS

    return (datetime.now(timezone.utc) - max(p["Timestamp"] for p in active)).days


def get_ec2_cpu_utilization(instance_id: str, days: int = METRIC_WINDOW_DAYS) -> float | None:
    points = _stat(instance_id, "CPUUtilization", "Average", days)
    if not points:
        return None
    return round(sum(p["Average"] for p in points) / len(points), 3)


def get_ec2_cpu_peak(instance_id: str, days: int = METRIC_WINDOW_DAYS) -> float | None:
    points = _stat(instance_id, "CPUUtilization", "Maximum", days)
    if not points:
        return None
    return round(max(p["Maximum"] for p in points), 3)


def get_ec2_network_bytes(instance_id: str, metric_name: str, days: int = METRIC_WINDOW_DAYS) -> float | None:
    points = _stat(instance_id, metric_name, "Sum", days)
    if not points:
        return None
    return sum(p["Sum"] for p in points)


def get_idle_days(instance_id: str, threshold_percent: float = 1.0) -> int | None:
    """Days since CPU last exceeded threshold. None when no data exists at all."""
    points = _stat(
        instance_id, "CPUUtilization", "Maximum",
        MAX_IDLE_LOOKBACK_DAYS, period=86400,
    )
    if not points:
        return None

    active = [p for p in points if p["Maximum"] > threshold_percent]
    if not active:
        return MAX_IDLE_LOOKBACK_DAYS

    last = max(p["Timestamp"] for p in active)
    return (datetime.now(timezone.utc) - last).days


def get_ec2_usage_evidence(instance_id: str, days: int = METRIC_WINDOW_DAYS) -> AWSEvidence:
    return AWSEvidence(
        metric_window_days=days,
        avg_cpu_percent=get_ec2_cpu_utilization(instance_id, days),
        max_cpu_percent=get_ec2_cpu_peak(instance_id, days),
        idle_days=get_idle_days(instance_id),
        network_in_bytes=get_ec2_network_bytes(instance_id, "NetworkIn", days),
        network_out_bytes=get_ec2_network_bytes(instance_id, "NetworkOut", days),
    )


# --- Per-type idle signals ---
# Each type reports the metric that actually indicates use. A NAT gateway has no
# CPU; a balancer with no requests is idle regardless of how healthy it looks.


def get_nat_usage_evidence(nat_id: str, days: int = METRIC_WINDOW_DAYS) -> AWSEvidence:
    bytes_out = _sum("AWS/NATGateway", "NatGatewayId", nat_id, "BytesOutToDestination", days)
    return AWSEvidence(
        metric_window_days=days,
        metric_source="NATGateway/BytesOutToDestination",
        bytes_processed=bytes_out,
        idle_days=_days_since_active(
            "AWS/NATGateway", "NatGatewayId", nat_id, "BytesOutToDestination"
        ),
    )


def _elb_dimension(arn: str) -> str:
    """CloudWatch wants the arn suffix (app/name/id), not the full arn."""
    parts = arn.split(":loadbalancer/")
    return parts[1] if len(parts) > 1 else arn


def get_elb_usage_evidence(
    arn: str, lb_type: str | None = None, days: int = METRIC_WINDOW_DAYS
) -> AWSEvidence:
    network = (lb_type or "").lower() == "network"
    namespace = "AWS/NetworkELB" if network else "AWS/ApplicationELB"
    metric = "ActiveFlowCount" if network else "RequestCount"
    dim = _elb_dimension(arn)

    return AWSEvidence(
        metric_window_days=days,
        metric_source=f"{namespace.split('/')[1]}/{metric}",
        request_count=_sum(namespace, "LoadBalancer", dim, metric, days),
        idle_days=_days_since_active(namespace, "LoadBalancer", dim, metric),
    )


def get_rds_usage_evidence(db_id: str, days: int = METRIC_WINDOW_DAYS) -> AWSEvidence:
    return AWSEvidence(
        metric_window_days=days,
        metric_source="RDS/DatabaseConnections",
        avg_cpu_percent=_avg("AWS/RDS", "DBInstanceIdentifier", db_id, "CPUUtilization", days),
        connection_count=_peak(
            "AWS/RDS", "DBInstanceIdentifier", db_id, "DatabaseConnections", days
        ),
        idle_days=_days_since_active(
            "AWS/RDS", "DBInstanceIdentifier", db_id, "DatabaseConnections"
        ),
    )


def get_cache_usage_evidence(cluster_id: str, days: int = METRIC_WINDOW_DAYS) -> AWSEvidence:
    return AWSEvidence(
        metric_window_days=days,
        metric_source="ElastiCache/CurrConnections",
        connection_count=_peak(
            "AWS/ElastiCache", "CacheClusterId", cluster_id, "CurrConnections", days
        ),
        bytes_processed=_sum(
            "AWS/ElastiCache", "CacheClusterId", cluster_id, "NetworkBytesOut", days
        ),
        idle_days=_days_since_active(
            "AWS/ElastiCache", "CacheClusterId", cluster_id, "CurrConnections"
        ),
    )
