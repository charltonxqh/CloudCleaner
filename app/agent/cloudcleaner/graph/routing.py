"""Conditional edges for the LangGraph workflow."""


def route_after_verify(state) -> str:
    verifications = state.get("verification_results") or []
    if not verifications:
        # Nothing was executed (blocked, not approved, or recommendation
        # wasn't "stop") - nothing to verify or roll back.
        return "complete"
    return "complete" if verifications[-1].verified else "rollback"
