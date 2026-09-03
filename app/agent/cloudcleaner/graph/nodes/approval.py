from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import ApprovalDecision


def approval_node(state: CloudCleanerState):
    return {
        "approval": ApprovalDecision(
            decision="approve",
            approved_by="demo-user",
            reason="Mock approval during development",
        )
    }