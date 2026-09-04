from cloudcleaner.schemas import AWSEvidence, CloudResource, Recommendation

IDLE_DAYS_HIGH = 30
IDLE_DAYS_MEDIUM = 14
CPU_IDLE_PERCENT = 2.0


def classify_severity(resource: CloudResource, aws: AWSEvidence) -> str:
    idle = aws.idle_days or 0
    cost = resource.estimated_monthly_cost or 0.0

    if resource.attached_to is None and resource.resource_type in ("ebs", "eip"):
        return "high" if cost > 3 else "medium"
    if resource.billing_while_stopped and idle >= IDLE_DAYS_HIGH:
        return "high"
    if idle >= IDLE_DAYS_HIGH and cost > 5:
        return "high"
    if idle >= IDLE_DAYS_MEDIUM:
        return "medium"
    return "low"


def rules_only_verdict(resource: CloudResource, aws: AWSEvidence) -> Recommendation:
    if resource.resource_type == "ebs" and resource.attached_to is None:
        return Recommendation(
            action="retire",
            reason=f"Volume is unattached ({resource.size_gb}GB) and bills whether used or not.",
            confidence=0.9,
        )

    if resource.resource_type == "eip" and resource.attached_to is None:
        return Recommendation(
            action="retire",
            reason="Elastic IP is not associated with any instance and bills hourly.",
            confidence=0.9,
        )

    if resource.resource_type == "snapshot":
        return Recommendation(
            action="investigate_more",
            reason="Snapshots may be the only restore point; confirm before deleting.",
            confidence=0.5,
        )

    idle = aws.idle_days
    cpu = aws.avg_cpu_percent

    if idle is None and cpu is None:
        return Recommendation(
            action="investigate_more",
            reason="No CloudWatch data available for this resource.",
            confidence=0.3,
        )

    if (idle or 0) >= IDLE_DAYS_HIGH and (cpu is None or cpu < CPU_IDLE_PERCENT):
        return Recommendation(
            action="retire",
            reason=f"Idle {idle} days with average CPU {cpu}%.",
            confidence=0.8,
        )

    if (idle or 0) >= IDLE_DAYS_MEDIUM:
        return Recommendation(
            action="stop",
            reason=f"Idle {idle} days.",
            confidence=0.6,
        )

    return Recommendation(
        action="keep",
        reason=f"Recent activity: average CPU {cpu}%, idle {idle} days.",
        confidence=0.7,
    )
