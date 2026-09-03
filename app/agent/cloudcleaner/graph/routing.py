"""Conditional edges for the LangGraph workflow."""


def route_after_verify(state) -> str:
    verification = state["verification_results"][-1]
    return "complete" if verification.verified else "rollback"
