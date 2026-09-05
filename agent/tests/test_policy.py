from datetime import datetime, timedelta, timezone

import pytest

from cloudcleaner.policy import evaluate_action
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.policy.risk import assess_risk
from cloudcleaner.policy.safety import NEEDS_APPROVAL_RISK_THRESHOLD, evaluate_safety
from cloudcleaner.schemas import (
    Action,
    ActionType,
    PolicyDecision,
    ResourceContext,
    RiskLevel,
)


def _ctx(**overrides) -> ResourceContext:
    defaults = dict(
        resource_id="i-0123456789abcdef0",
        region="us-east-1",
        tags={"Environment": "dev", "Owner": "amanda"},
        state="running",
        last_state_change=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    defaults.update(overrides)
    return ResourceContext(**defaults)


def _stop_action(**overrides) -> Action:
    defaults = dict(
        action_type=ActionType.STOP_INSTANCE,
        resource_id="i-0123456789abcdef0",
        region="us-east-1",
        reason="idle",
    )
    defaults.update(overrides)
    return Action(**defaults)


@pytest.fixture(autouse=True)
def _reset_metrics():
    METRICS.reset()
    yield
    METRICS.reset()


def test_safety_prod_stop_needs_approval_not_blocked():
    # Prod no longer hard-blocks - it goes through the normal approval flow,
    # just with a higher bar (see test below).
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "prod", "Owner": "amanda"})
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.decision == PolicyDecision.NEEDS_APPROVAL


def test_safety_prod_stop_requires_one_approval():
    # Prod goes through the same single-approval tier as any other
    # NEEDS_APPROVAL case - no special-casing.
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "prod", "Owner": "amanda"})
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.required_approvals == 1


def test_safety_non_prod_needs_approval_requires_one_approval():
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "staging", "Owner": "amanda"}, recent_activity=True)
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.decision == PolicyDecision.NEEDS_APPROVAL
    assert result.required_approvals == 1


def test_safety_allow_has_zero_required_approvals():
    action = _stop_action()
    ctx = _ctx()  # dev, owned, low risk -> ALLOW
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.decision == PolicyDecision.ALLOW
    assert result.required_approvals == 0


def test_safety_force_override_suppresses_missing_owner_violation():
    action = _stop_action(force_override=True)
    ctx = _ctx(tags={"Environment": "dev"})  # no Owner tag
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert not any(v.rule == "require_owner_tag" for v in result.violations)


def test_safety_flags_missing_owner_tag_as_soft_violation():
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "dev"})
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    violation = next(v for v in result.violations if v.rule == "require_owner_tag")
    assert violation.hard_block is False
    assert result.decision == PolicyDecision.NEEDS_APPROVAL


def test_safety_blocks_stop_within_cooldown_window():
    action = _stop_action()
    ctx = _ctx(last_state_change=datetime.now(timezone.utc) - timedelta(minutes=5))
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.decision == PolicyDecision.BLOCK
    assert any(v.rule == "block_stop_recently_started" for v in result.violations)


def test_safety_needs_approval_when_no_hard_block_but_medium_risk():
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "staging", "Owner": "amanda"}, recent_activity=True)
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.risk_assessment.risk_score >= NEEDS_APPROVAL_RISK_THRESHOLD
    assert result.decision == PolicyDecision.NEEDS_APPROVAL


def test_safety_score_just_below_threshold_allows():
    action = _stop_action()
    ctx = _ctx(
        tags={"Environment": "staging", "Owner": "amanda"},
        recent_activity=False,
        estimated_monthly_cost_usd=45.0,
    )
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.risk_assessment.risk_score == NEEDS_APPROVAL_RISK_THRESHOLD - 1
    assert result.decision == PolicyDecision.ALLOW


def test_safety_score_exactly_at_threshold_needs_approval():
    action = _stop_action()
    ctx = _ctx(
        tags={"Environment": "staging", "Owner": "amanda"},
        recent_activity=False,
        estimated_monthly_cost_usd=50.0,
    )
    result = evaluate_safety(action, ctx, assess_risk(action, ctx))
    assert result.risk_assessment.risk_score == NEEDS_APPROVAL_RISK_THRESHOLD
    assert result.decision == PolicyDecision.NEEDS_APPROVAL


def test_risk_score_low_for_owned_dev_instance_with_no_activity():
    action = _stop_action()
    ctx = _ctx(tags={"Environment": "dev", "Owner": "amanda"}, recent_activity=False)
    risk = assess_risk(action, ctx)
    assert risk.risk_level == RiskLevel.LOW


def test_risk_score_high_for_expensive_staging_instance_with_activity():
    action = _stop_action()
    ctx = _ctx(
        tags={"Environment": "staging", "Owner": "amanda"},
        recent_activity=True,
        estimated_monthly_cost_usd=200.0,
    )
    risk = assess_risk(action, ctx)
    assert risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_risk_score_increases_when_github_pr_still_open():
    action = _stop_action()
    base = dict(tags={"Environment": "dev", "Owner": "amanda"}, recent_activity=False)
    with_open_pr = assess_risk(action, _ctx(**base, github_pr_open=True))
    without_evidence = assess_risk(action, _ctx(**base, github_pr_open=None))
    assert with_open_pr.risk_score == without_evidence.risk_score + 20
    assert any("GitHub" in reason for reason in with_open_pr.reasons)


def test_risk_score_unaffected_when_github_pr_closed():
    action = _stop_action()
    base = dict(tags={"Environment": "dev", "Owner": "amanda"}, recent_activity=False)
    closed = assess_risk(action, _ctx(**base, github_pr_open=False))
    without_evidence = assess_risk(action, _ctx(**base, github_pr_open=None))
    assert closed.risk_score == without_evidence.risk_score


@pytest.mark.parametrize(
    "score,expected",
    [(24, RiskLevel.LOW), (25, RiskLevel.MEDIUM), (49, RiskLevel.MEDIUM),
     (50, RiskLevel.HIGH), (74, RiskLevel.HIGH), (75, RiskLevel.CRITICAL)],
)
def test_risk_level_thresholds_boundaries(score, expected):
    from cloudcleaner.policy.risk import _level_for_score

    assert _level_for_score(score) == expected


def test_metrics_increment_on_evaluate_action():
    action = _stop_action()
    ctx = _ctx()
    evaluate_action(action, ctx)
    assert sum(METRICS.summary().values()) == 1
