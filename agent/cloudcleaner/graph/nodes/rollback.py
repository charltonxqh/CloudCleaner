"""ROLLBACK node.

Trigger matrix:
- STOP verification failed -> attempt start_instance to restore the prior
  running state, then re-verify.
- START verification failed -> nothing destructive happened yet (the
  instance was already stopped), so retry the start up to
  ROLLBACK_MAX_RETRIES times; if it still doesn't verify, escalate to a
  human rather than retrying forever.
"""

from cloudcleaner.config import settings
from cloudcleaner.graph.nodes.verify import verify_action
from cloudcleaner.policy.metrics import METRICS
from cloudcleaner.schemas import (
    Action,
    ActionType,
    RollbackResult,
    VerificationResult,
)
from cloudcleaner.tools.aws.actions import execute_start_instance, propose_start_instance


def _restart_after_failed_stop(original_action: Action) -> RollbackResult:
    rollback = propose_start_instance(
        original_action.resource_id,
        original_action.region,
        reason=f"auto-rollback of failed stop {original_action.id}",
    )
    exec_result = execute_start_instance(rollback)
    rb_verify = verify_action(rollback)
    escalated = not rb_verify.verified

    METRICS.record("rollback_escalated" if escalated else "rolled_back")
    return RollbackResult(
        original_action_id=original_action.id,
        rollback_action=rollback,
        rollback_execution=exec_result,
        rollback_verification=rb_verify,
        trigger_reason="stop verification failed",
        escalated=escalated,
    )


def _retry_after_failed_start(original_action: Action) -> RollbackResult:
    retry: Action | None = None
    exec_result = None
    rb_verify: VerificationResult | None = None

    for attempt in range(settings.ROLLBACK_MAX_RETRIES):
        retry = propose_start_instance(
            original_action.resource_id,
            original_action.region,
            reason=f"retry {attempt + 1} after failed start {original_action.id}",
        )
        exec_result = execute_start_instance(retry)
        rb_verify = verify_action(retry)
        if rb_verify.verified:
            METRICS.record("rolled_back")
            return RollbackResult(
                original_action_id=original_action.id,
                rollback_action=retry,
                rollback_execution=exec_result,
                rollback_verification=rb_verify,
                trigger_reason="start verification failed",
                escalated=False,
            )

    METRICS.record("rollback_escalated")
    return RollbackResult(
        original_action_id=original_action.id,
        rollback_action=retry,
        rollback_execution=exec_result,
        rollback_verification=rb_verify,
        trigger_reason="start verification failed after retries",
        escalated=True,
    )


def rollback_action(original_action: Action, verification: VerificationResult) -> RollbackResult:
    if original_action.action_type == ActionType.STOP_INSTANCE:
        return _restart_after_failed_stop(original_action)
    return _retry_after_failed_start(original_action)


def rollback_node(state) -> dict:
    action = state["pending_action"]
    verification = state["verification_results"][-1]
    result = rollback_action(action, verification)
    return {"rollback_results": [result]}
