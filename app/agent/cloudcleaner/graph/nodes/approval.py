from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import ApprovalDecision


def approval_node(state: CloudCleanerState):
    # Tracks how many times this node has run for the current action, so
    # routing.route_after_approval knows when enough rounds have been
    # collected (currently always 1 - see policy/safety.py). Still a mock
    # decision (always "approve") until real human-in-the-loop approval
    # (e.g. Slack) is wired in.
    rounds = state.get("approval_rounds", 0) + 1
    return {
        "approval": ApprovalDecision(
            decision="approve",
            approved_by="demo-user",
            reason=f"Mock approval during development (round {rounds})",
        ),
        "approval_rounds": rounds,
    }