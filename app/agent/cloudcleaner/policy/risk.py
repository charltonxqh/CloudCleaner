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
