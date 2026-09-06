"""On-demand us-east-1 list prices with AWS Price List API lookup and local fallbacks."""

from cloudcleaner.config import AWS_REGION
from cloudcleaner.tools.aws.pricing import get_ebs_gb_month_price, get_ec2_hourly_price

HOURS_PER_MONTH = 730

EC2_HOURLY = {
    "t2.micro": 0.0116,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "m5.large": 0.096,
    "c5.large": 0.085,
}
EC2_HOURLY_DEFAULT = 0.05

EBS_GB_MONTH = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}
EBS_GB_MONTH_DEFAULT = 0.08

SNAPSHOT_GB_MONTH = 0.05
PUBLIC_IPV4_HOURLY = 0.005

NAT_GATEWAY_HOURLY = 0.045
NAT_GB_PROCESSED = 0.045

# Base hourly rate only. LCU/capacity-unit charges scale with traffic, and an
# idle balancer has none, so the base rate is the whole bill for the cases we act on.
ELB_HOURLY = {
    "application": 0.0225,
    "network": 0.0225,
    "gateway": 0.0125,
    "classic": 0.025,
}
ELB_HOURLY_DEFAULT = 0.0225

RDS_HOURLY = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t4g.micro": 0.016,
    "db.t4g.small": 0.032,
    "db.m5.large": 0.171,
    "db.r5.large": 0.24,
}
RDS_HOURLY_DEFAULT = 0.05
RDS_STORAGE_GB_MONTH = {"gp2": 0.115, "gp3": 0.115, "io1": 0.125, "standard": 0.10}
RDS_STORAGE_GB_MONTH_DEFAULT = 0.115
RDS_BACKUP_GB_MONTH = 0.095

ELASTICACHE_HOURLY = {
    "cache.t3.micro": 0.017,
    "cache.t3.small": 0.034,
    "cache.t3.medium": 0.068,
    "cache.t4g.micro": 0.016,
    "cache.m5.large": 0.156,
    "cache.r5.large": 0.216,
}
ELASTICACHE_HOURLY_DEFAULT = 0.05


def ec2_compute_cost(instance_type: str | None) -> float:
    hourly = get_ec2_hourly_price(instance_type or "", AWS_REGION)
    if hourly is None:
        hourly = EC2_HOURLY.get(instance_type or "", EC2_HOURLY_DEFAULT)
    return round(hourly * HOURS_PER_MONTH, 2)


def ebs_cost(size_gb: int | None, volume_type: str | None = None) -> float:
    if not size_gb:
        return 0.0
    rate = get_ebs_gb_month_price(volume_type or "", AWS_REGION)
    if rate is None:
        rate = EBS_GB_MONTH.get(volume_type or "", EBS_GB_MONTH_DEFAULT)
    return round(size_gb * rate, 2)


def snapshot_cost(size_gb: int | None) -> float:
    return round((size_gb or 0) * SNAPSHOT_GB_MONTH, 2)


def public_ipv4_cost() -> float:
    return round(PUBLIC_IPV4_HOURLY * HOURS_PER_MONTH, 2)


def instance_cost(
    state: str | None,
    instance_type: str | None,
    attached_volumes_gb: int = 0,
    has_public_ip: bool = False,
) -> tuple[float, bool]:
    """Returns (monthly cost, whether it is still billing while stopped).

    Stopping releases compute only. Storage and the public IPv4 keep billing.
    """
    storage = ebs_cost(attached_volumes_gb)
    address = public_ipv4_cost() if has_public_ip else 0.0

    if state == "running":
        return round(ec2_compute_cost(instance_type) + storage + address, 2), False

    residual = round(storage + address, 2)
    return residual, residual > 0


def instance_cost_if_stopped(
    attached_volumes_gb: int = 0,
    has_public_ip: bool = False,
) -> float:
    storage = ebs_cost(attached_volumes_gb)
    address = public_ipv4_cost() if has_public_ip else 0.0
    return round(storage + address, 2)


def instance_monthly_saving_if_stopped(
    state: str | None,
    instance_type: str | None,
    attached_volumes_gb: int = 0,
    has_public_ip: bool = False,
) -> float:
    if state != "running":
        return 0.0
    current, _ = instance_cost(state, instance_type, attached_volumes_gb, has_public_ip)
    stopped = instance_cost_if_stopped(attached_volumes_gb, has_public_ip)
    return round(max(current - stopped, 0.0), 2)


def nat_gateway_cost(gb_processed_per_month: float = 0.0) -> float:
    """Hourly charge applies to an idle gateway too; data processing is on top."""
    return round(
        NAT_GATEWAY_HOURLY * HOURS_PER_MONTH + gb_processed_per_month * NAT_GB_PROCESSED, 2
    )


def load_balancer_cost(lb_type: str | None) -> float:
    rate = ELB_HOURLY.get((lb_type or "").lower(), ELB_HOURLY_DEFAULT)
    return round(rate * HOURS_PER_MONTH, 2)


def rds_storage_cost(size_gb: int | None, storage_type: str | None = None) -> float:
    if not size_gb:
        return 0.0
    rate = RDS_STORAGE_GB_MONTH.get(
        (storage_type or "").lower(), RDS_STORAGE_GB_MONTH_DEFAULT
    )
    return round(size_gb * rate, 2)


def rds_cost(
    state: str | None,
    instance_class: str | None,
    storage_gb: int | None = 0,
    storage_type: str | None = None,
    backup_gb: float = 0.0,
    multi_az: bool = False,
) -> tuple[float, bool]:
    """Returns (monthly cost, whether it is still billing while stopped).

    The EC2 trap, one level worse: a stopped RDS instance keeps billing for its
    allocated storage and backups, and AWS restarts it automatically after 7 days.
    """
    storage = rds_storage_cost(storage_gb, storage_type)
    backups = round(backup_gb * RDS_BACKUP_GB_MONTH, 2)
    residual = round(storage + backups, 2)

    if state in ("stopped", "stopping"):
        return residual, residual > 0

    hourly = RDS_HOURLY.get((instance_class or "").lower(), RDS_HOURLY_DEFAULT)
    compute = hourly * HOURS_PER_MONTH * (2 if multi_az else 1)
    return round(compute + residual, 2), False


def rds_monthly_saving_if_stopped(
    state: str | None,
    instance_class: str | None,
    storage_gb: int | None = 0,
    storage_type: str | None = None,
    backup_gb: float = 0.0,
    multi_az: bool = False,
) -> float:
    """Capped at 7 days: AWS force-starts a stopped instance after that."""
    if state != "available":
        return 0.0
    current, _ = rds_cost(state, instance_class, storage_gb, storage_type, backup_gb, multi_az)
    stopped, _ = rds_cost("stopped", instance_class, storage_gb, storage_type, backup_gb, multi_az)
    return round(max(current - stopped, 0.0) * (7 / 30), 2)


def elasticache_cost(node_type: str | None, node_count: int = 1) -> float:
    rate = ELASTICACHE_HOURLY.get((node_type or "").lower(), ELASTICACHE_HOURLY_DEFAULT)
    return round(rate * HOURS_PER_MONTH * max(node_count, 1), 2)
