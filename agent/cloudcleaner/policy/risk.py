"""Deterministic risk/impact scoring. Pure functions, no AWS calls, no LLM."""

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

from cloudcleaner.schemas import AWSEvidence, CloudResource, Recommendation  # noqa: E402

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
        return Recommendation(action="stop", reason=f"Idle {idle} days.", confidence=0.6)

    return Recommendation(
        action="keep",
        reason=f"Recent activity: average CPU {cpu}%, idle {idle} days.",
        confidence=0.7,
    )
