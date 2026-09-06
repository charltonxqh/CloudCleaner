"""Deterministic risk/impact scoring. Pure functions, no AWS calls, no LLM."""

from datetime import datetime, timezone

from cloudcleaner.schemas import Action, ActionType, ResourceContext, RiskAssessment, RiskLevel


def _level_for_score(score: int) -> RiskLevel:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def score_stop_instance(action: Action, ctx: ResourceContext) -> RiskAssessment:
    score = 0
    reasons: list[str] = []

    env = ctx.tags.get("Environment", ctx.tags.get("env", "")).lower()
    if env in {"staging", "stage"}:
        score += 30
        reasons.append("staging environment")
    elif env in {"prod", "production"}:
        score += 40
        reasons.append("prod environment")

    if not (ctx.tags.get("Owner") or ctx.tags.get("owner")):
        score += 20
        reasons.append("no Owner tag")

    if ctx.age_days is not None and ctx.age_days < 1:
        score += 15
        reasons.append("instance younger than 1 day")

    if ctx.recent_activity:
        score += 25
        reasons.append("recent CPU/network activity observed")
    elif ctx.recent_activity is None:
        score += 10
        reasons.append("activity unknown - treated conservatively")

    if ctx.estimated_monthly_cost_usd:
        score += min(int(ctx.estimated_monthly_cost_usd // 10), 20)
        reasons.append(f"est. cost ${ctx.estimated_monthly_cost_usd:.2f}/mo")

    if ctx.github_pr_open:
        score += 20
        reasons.append("related GitHub branch/PR still active")

    score = min(score, 100)
    return RiskAssessment(
        action_id=action.id, risk_score=score, risk_level=_level_for_score(score), reasons=reasons
    )


def score_start_instance(action: Action, ctx: ResourceContext) -> RiskAssessment:
    # Starting is inherently reversible (can be re-stopped); low baseline risk.
    score = 5
    reasons = ["start actions are low-risk / reversible"]
    return RiskAssessment(
        action_id=action.id, risk_score=score, risk_level=_level_for_score(score), reasons=reasons
    )


_SCORERS = {
    ActionType.STOP_INSTANCE: score_stop_instance,
    ActionType.START_INSTANCE: score_start_instance,
}


def assess_risk(action: Action, ctx: ResourceContext) -> RiskAssessment:
    return _SCORERS[action.action_type](action, ctx)


# --- Teardown severity ---
# Owned by: graph/nodes/{assess,plan}.py
#
# assess_risk() above scores a proposed Action for the policy gate. This scores
# the *resource* for display and for the rules-only fallback when the LLM is off,
# so it takes evidence rather than an Action.

from cloudcleaner.schemas import AWSEvidence, CloudResource, GitHubEvidence, Recommendation  # noqa: E402

IDLE_DAYS_HIGH = 30
IDLE_DAYS_MEDIUM = 14
CPU_IDLE_PERCENT = 2.0


def _within_days(value: str | None, days: int) -> bool:
    if not value:
        return False
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - timestamp).total_seconds() <= days * 86400


def _active_github_reason(github: GitHubEvidence | None) -> str | None:
    if github is None:
        return None

    if github.branch_exists is True and github.pr_status not in {"merged", "closed"}:
        return "related GitHub branch/PR is still active"
    if github.scheduled_workflow_exists is True:
        return "repository has a scheduled GitHub Actions workflow"
    if _within_days(github.last_workflow_run_at, IDLE_DAYS_MEDIUM):
        return f"GitHub Actions ran within the last {IDLE_DAYS_MEDIUM} days"
    return None


def classify_severity(resource: CloudResource, aws: AWSEvidence) -> str:
    idle = aws.idle_days or 0
    cost = resource.estimated_monthly_cost or 0.0

    if resource.attached_to is None and resource.resource_type in ("ebs", "eip"):
        return "high" if cost > 3 else "medium"

    if resource.resource_type == "snapshot":
        # Snapshots emit no metrics, so age is the only usable signal.
        from cloudcleaner.policy.safety import _age_days

        age = _age_days(resource) or 0
        if resource.image_ids:
            return "medium"
        return "high" if age >= IDLE_SNAPSHOT_DAYS and cost > 3 else "medium"

    if resource.resource_type in ("nat", "elb", "cache") and idle >= IDLE_DAYS_MEDIUM:
        # No stopped state exists for these, so idle time is money already gone.
        return "high" if cost > 10 else "medium"
    if resource.billing_while_stopped and idle >= IDLE_DAYS_HIGH:
        return "high"
    if idle >= IDLE_DAYS_HIGH and cost > 5:
        return "high"
    if idle >= IDLE_DAYS_MEDIUM:
        return "medium"
    return "low"


def rules_only_verdict(
    resource: CloudResource,
    aws: AWSEvidence,
    github: GitHubEvidence | None = None,
) -> Recommendation:
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

    verdict = _typed_verdict(resource, aws)
    if verdict is not None:
        return verdict

    github_reason = _active_github_reason(github)
    if github_reason:
        return Recommendation(
            action="keep",
            reason=f"GitHub/CI/CD evidence shows ongoing use: {github_reason}.",
            confidence=0.85,
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
        if github is not None and _within_days(github.latest_commit_at, IDLE_DAYS_MEDIUM):
            return Recommendation(
                action="stop",
                reason=(
                    f"Idle {idle} days with average CPU {cpu}%, but the linked repository "
                    f"has a commit within the last {IDLE_DAYS_MEDIUM} days."
                ),
                confidence=0.65,
            )
        return Recommendation(
            action="retire",
            reason=f"Idle {idle} days with average CPU {cpu}%.",
            confidence=0.8,
        )

    if (idle or 0) >= IDLE_DAYS_MEDIUM:
        return Recommendation(action="stop", reason=f"Idle {idle} days.", confidence=0.6)

    return Recommendation(
        action="keep",
        reason=f"Recent activity: average CPU {cpu}%, idle {idle} days.",
        confidence=0.7,
    )


# --- Per-type rules for the resources that have no CPU metric ---
# CPU is the EC2 signal. A NAT gateway, a balancer, a database and a cache each
# publish something different, and none of them can be judged by CPU absence.

IDLE_SNAPSHOT_DAYS = 90


def _idle(aws: AWSEvidence) -> int:
    return aws.idle_days or 0


def _nat_verdict(resource, aws) -> Recommendation:
    if aws.bytes_processed is None:
        return Recommendation(
            action="investigate_more",
            reason="No NAT gateway traffic metrics available for this window.",
            confidence=0.3,
        )

    if aws.bytes_processed == 0 and _idle(aws) >= IDLE_DAYS_MEDIUM:
        return Recommendation(
            action="retire",
            reason=(
                f"NAT gateway has passed no traffic for {_idle(aws)} days and costs "
                f"${resource.estimated_monthly_cost}/mo. It cannot be stopped, only deleted."
            ),
            confidence=0.85,
        )

    return Recommendation(
        action="keep",
        reason=f"NAT gateway processed {aws.bytes_processed:,.0f} bytes in the window.",
        confidence=0.7,
    )


def _elb_verdict(resource, aws) -> Recommendation:
    if aws.request_count is None:
        return Recommendation(
            action="investigate_more",
            reason="No load balancer request metrics available for this window.",
            confidence=0.3,
        )

    if aws.request_count == 0 and _idle(aws) >= IDLE_DAYS_MEDIUM:
        return Recommendation(
            action="retire",
            reason=(
                f"Load balancer has served no requests for {_idle(aws)} days and still bills "
                f"${resource.estimated_monthly_cost}/mo for its hourly base rate."
            ),
            confidence=0.85,
        )

    return Recommendation(
        action="keep",
        reason=f"Load balancer served {aws.request_count:,.0f} requests in the window.",
        confidence=0.7,
    )


def _rds_verdict(resource, aws) -> Recommendation:
    # A stopped RDS instance is the worst case: it bills for storage and AWS
    # restarts it after 7 days, so "stopped" is a bill with a timer on it.
    if resource.state in ("stopped", "stopping"):
        return Recommendation(
            action="retire",
            reason=(
                f"Database is stopped but still bills ${resource.estimated_monthly_cost}/mo for "
                f"{resource.size_gb or 0}GB of storage, and AWS restarts it automatically "
                "7 days after it was stopped."
            ),
            confidence=0.8,
        )

    if aws.connection_count is None:
        return Recommendation(
            action="investigate_more",
            reason="No RDS connection metrics available for this window.",
            confidence=0.3,
        )

    if aws.connection_count == 0 and _idle(aws) >= IDLE_DAYS_HIGH:
        return Recommendation(
            action="retire",
            reason=f"Database has accepted no connections for {_idle(aws)} days.",
            confidence=0.75,
        )

    if aws.connection_count == 0 and _idle(aws) >= IDLE_DAYS_MEDIUM:
        return Recommendation(
            action="stop",
            reason=(
                f"No connections for {_idle(aws)} days. Stopping buys 7 days before AWS "
                "restarts it, and storage keeps billing throughout."
            ),
            confidence=0.6,
        )

    return Recommendation(
        action="keep",
        reason=f"Database peaked at {aws.connection_count:,.0f} connections in the window.",
        confidence=0.7,
    )


def _cache_verdict(resource, aws) -> Recommendation:
    if aws.connection_count is None:
        return Recommendation(
            action="investigate_more",
            reason="No ElastiCache connection metrics available for this window.",
            confidence=0.3,
        )

    if aws.connection_count == 0 and _idle(aws) >= IDLE_DAYS_MEDIUM:
        return Recommendation(
            action="retire",
            reason=(
                f"Cache has had no client connections for {_idle(aws)} days. ElastiCache has "
                f"no stopped state, so its ${resource.estimated_monthly_cost}/mo runs until "
                "the cluster is deleted."
            ),
            confidence=0.8,
        )

    return Recommendation(
        action="keep",
        reason=f"Cache peaked at {aws.connection_count:,.0f} connections in the window.",
        confidence=0.7,
    )


def _snapshot_verdict(resource, aws) -> Recommendation:
    if resource.image_ids:
        return Recommendation(
            action="investigate_more",
            reason=(
                f"Snapshot backs {len(resource.image_ids)} AMI(s) "
                f"({', '.join(resource.image_ids)}); each has to be deregistered "
                "before the snapshot can go."
            ),
            confidence=0.5,
        )

    from cloudcleaner.policy.safety import _age_days

    age = _age_days(resource)
    if age is not None and age >= IDLE_SNAPSHOT_DAYS:
        return Recommendation(
            action="retire",
            reason=(
                f"{resource.size_gb or 0}GB snapshot is {age} days old, nothing references it, "
                "and it has billed every day since it was taken."
            ),
            confidence=0.7,
        )

    return Recommendation(
        action="investigate_more",
        reason="Snapshots may be the only restore point; confirm before deleting.",
        confidence=0.5,
    )


_TYPED_VERDICTS = {
    "nat": _nat_verdict,
    "elb": _elb_verdict,
    "rds": _rds_verdict,
    "cache": _cache_verdict,
    "snapshot": _snapshot_verdict,
}


def _typed_verdict(resource: CloudResource, aws: AWSEvidence) -> Recommendation | None:
    fn = _TYPED_VERDICTS.get(resource.resource_type)
    return fn(resource, aws) if fn else None
