from langgraph.graph import END, START, StateGraph

from cloudcleaner.graph.nodes.approval import approval_node
from cloudcleaner.graph.nodes.assess import assess_node
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.graph.nodes.execute import execute_node
from cloudcleaner.graph.nodes.investigate import investigate_node
from cloudcleaner.graph.nodes.policy_check import policy_check_node
from cloudcleaner.graph.nodes.rollback import rollback_node
from cloudcleaner.graph.nodes.verify import verify_node
from cloudcleaner.graph.routing import route_after_approval, route_after_policy_check, route_after_verify
from cloudcleaner.graph.state import CloudCleanerState


def build_graph():
    builder = StateGraph(CloudCleanerState)

    builder.add_node("detect", detect_node)
    builder.add_node("investigate", investigate_node)
    builder.add_node("assess", assess_node)
    builder.add_node("policy_check", policy_check_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)
    builder.add_node("verify", verify_node)
    builder.add_node("rollback", rollback_node)

    builder.add_edge(START, "detect")
    builder.add_edge("detect", "investigate")
    builder.add_edge("investigate", "assess")
    builder.add_edge("assess", "policy_check")
    builder.add_conditional_edges(
        "policy_check", route_after_policy_check, {"approval": "approval", "execute": "execute"}
    )
    builder.add_conditional_edges(
        "approval", route_after_approval, {"approval": "approval", "execute": "execute"}
    )
    builder.add_edge("execute", "verify")
    builder.add_conditional_edges(
        "verify", route_after_verify, {"complete": END, "rollback": "rollback"}
    )
    builder.add_edge("rollback", END)

    return builder.compile()


graph = build_graph()
