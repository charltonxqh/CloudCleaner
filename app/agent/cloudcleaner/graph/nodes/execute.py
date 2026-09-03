from cloudcleaner.graph.state import CloudCleanerState


def execute_node(state: CloudCleanerState):
    if state["approval"].decision != "approve":
        return {
            "action_result": "No action executed."
        }

    return {
        "action_result": "MOCK: EC2 instance stopped."
    }