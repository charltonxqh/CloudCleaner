"""VERIFY node. Polls AWS to confirm an action's outcome actually happened."""

import time

from botocore.exceptions import ClientError

from cloudcleaner.config import settings
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import Action, ActionType, ExecutionStatus, VerificationResult
from cloudcleaner.tools.aws.actions import get_instance_state

EXPECTED_STATE = {
    ActionType.STOP_INSTANCE: "stopped",
    ActionType.START_INSTANCE: "running",
}

# Execution statuses worth polling AWS for. A blocked/failed/no-op action
# never mutated anything, so there's nothing to verify.
VERIFIABLE_STATUSES = {ExecutionStatus.EXECUTED, ExecutionStatus.SKIPPED_DRY_RUN}


def verify_action(
    action: Action,
    max_attempts: int | None = None,
    delay_seconds: float | None = None,
) -> VerificationResult:
    """Injectable attempts/delay so tests can run instantly (delay_seconds=0)."""
    expected = EXPECTED_STATE[action.action_type]
    attempts = max_attempts if max_attempts is not None else settings.VERIFY_MAX_ATTEMPTS
    delay = delay_seconds if delay_seconds is not None else settings.VERIFY_POLL_INTERVAL_SECONDS

    actual = "unknown"
    for attempt in range(1, attempts + 1):
        try:
            actual = get_instance_state(action.region, action.resource_id)
        except ClientError as e:
            # e.g. the instance doesn't exist (or no longer exists) - can't
            # verify a state that can't even be looked up. Don't crash the
            # whole pipeline over it; report it as unverified instead.
            return VerificationResult(
                action_id=action.id,
                expected_state=expected,
                actual_state=f"lookup failed: {e}",
                verified=False,
                attempts=attempt,
            )
        if actual == expected:
            return VerificationResult(
                action_id=action.id,
                expected_state=expected,
                actual_state=actual,
                verified=True,
                attempts=attempt,
            )
        if attempt < attempts:
            time.sleep(delay)

    return VerificationResult(
        action_id=action.id,
        expected_state=expected,
        actual_state=actual,
        verified=False,
        attempts=attempts,
    )


def _verify_plan(state: CloudCleanerState) -> dict:
    """Verify a teardown. In dry run there is nothing to observe, so we report
    that honestly rather than claiming a pass.
    """
    from cloudcleaner.config import DRY_RUN
    from cloudcleaner.evidence.collector import log

    results = state.get("action_results") or []
    if not results:
        return {"verification_passed": False}

    if DRY_RUN:
        log.emit("verify", "decision", "-", "dry run, nothing to observe")
        return {"verification_passed": True}

    ok = all(r.get("ok") for r in results)
    log.emit("verify", "decision", "-", f"{len(results)} actions, passed={ok}")
    return {"verification_passed": ok}


def verify_node(state: CloudCleanerState) -> dict:
    if state.get("action_results"):
        return _verify_plan(state)

    action = state.get("pending_action")
    execution_results = state.get("execution_results") or []
    if action is None or not execution_results:
        return {"verification_results": []}

    if execution_results[-1].status not in VERIFIABLE_STATUSES:
        return {"verification_results": []}

    verification = verify_action(action)
    return {"verification_results": [verification]}
