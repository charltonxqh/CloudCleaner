from datetime import datetime, timedelta, timezone

from cloudcleaner.config import METRIC_WINDOW_DAYS
from cloudcleaner.schemas import AWSEvidence
from cloudcleaner.tools.aws.client import get_cloudwatch_client

MAX_IDLE_LOOKBACK_DAYS = 90


def _window(days: int):
    end = datetime.now(timezone.utc)
    return end - timedelta(days=days), end


def _stat(instance_id: str, metric: str, stat: str, days: int, period: int = 3600):
    start, end = _window(days)
    resp = get_cloudwatch_client().get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metric,
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=period,
        Statistics=[stat],
    )
    return resp["Datapoints"]


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
