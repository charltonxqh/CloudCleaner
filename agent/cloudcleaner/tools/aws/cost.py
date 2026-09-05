"""On-demand us-east-1 list prices. Verify against the AWS pricing page before citing."""

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


def ec2_compute_cost(instance_type: str | None) -> float:
    hourly = EC2_HOURLY.get(instance_type or "", EC2_HOURLY_DEFAULT)
    return round(hourly * HOURS_PER_MONTH, 2)


def ebs_cost(size_gb: int | None, volume_type: str | None = None) -> float:
    if not size_gb:
        return 0.0
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
