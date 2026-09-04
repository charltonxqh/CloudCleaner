from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from cloudcleaner.graph.nodes.approval import approval_node
from cloudcleaner.graph.nodes.assess import assess_node
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.graph.nodes.execute import execute_node
from cloudcleaner.graph.nodes.investigate import investigate_node
from cloudcleaner.graph.nodes.plan import plan_node
from cloudcleaner.graph.nodes.record import record_node
from cloudcleaner.graph.nodes.verify import verify_node
from cloudcleaner.graph.routing import (
    after_approval,
    after_assess,
    after_detect,
    after_plan,
)
from cloudcleaner.graph.state import CloudCleanerState


def build_graph(checkpointer=None):
    builder = StateGraph(CloudCleanerState)

    builder.add_node("detect", detect_node)
    builder.add_node("investigate", investigate_node)
    builder.add_node("assess", assess_node)
    builder.add_node("plan", plan_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)
    builder.add_node("verify", verify_node)
    builder.add_node("record", record_node)

    builder.add_edge(START, "detect")
    builder.add_conditional_edges("detect", after_detect, {"investigate": "investigate", "end": END})
    builder.add_edge("investigate", "assess")
    builder.add_conditional_edges("assess", after_assess, {"plan": "plan", "record": "record"})
    builder.add_conditional_edges("plan", after_plan, {"approval": "approval", "record": "record"})
    builder.add_conditional_edges("approval", after_approval, {"execute": "execute", "record": "record"})
    builder.add_edge("execute", "verify")
    builder.add_edge("verify", "record")
    builder.add_edge("record", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


graph = build_graph()
