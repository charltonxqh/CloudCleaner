from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.policy.risk import assess_risk
from cloudcleaner.policy.safety import evaluate_safety
from cloudcleaner.schemas import Action, PolicyResult, ResourceContext


def evaluate_action(action: Action, ctx: ResourceContext) -> PolicyResult:
    risk = assess_risk(action, ctx)
    result = evaluate_safety(action, ctx, risk)
    METRICS.record(result.decision.value)
    return result
