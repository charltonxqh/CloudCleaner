from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from cloudcleaner.graph.nodes.approval import approval_node
from cloudcleaner.graph.nodes.assess import assess_node
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.graph.nodes.execute import execute_node
from cloudcleaner.graph.nodes.investigate import investigate_node
from cloudcleaner.graph.nodes.plan import plan_node
from cloudcleaner.graph.nodes.policy_check import policy_check_node
from cloudcleaner.graph.nodes.record import record_node
from cloudcleaner.graph.nodes.rollback import rollback_node
from cloudcleaner.graph.nodes.verify import verify_node
from cloudcleaner.graph.routing import (
    route_after_assess,
    route_after_detect,
    route_after_plan,
    route_after_approval,
    route_after_policy_check,
    route_after_verify,
)
from cloudcleaner.graph.state import CloudCleanerState


def _default_checkpointer():
    """Persist paused runs so an approval survives an agent restart.

    Falls back to memory if the file cannot be opened - a demo on a read-only
    filesystem should still work, it just forgets interrupted runs.
    """
    import sqlite3

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from cloudcleaner.storage.db import DB_PATH

    # Declare our own models rather than deserialising whatever the checkpoint
    # file happens to contain.
    from cloudcleaner import schemas

    allowed = [
        getattr(schemas, n) for n in dir(schemas)
        if isinstance(getattr(schemas, n), type) and getattr(schemas, n).__module__
        == "cloudcleaner.schemas"
    ]
    serde = JsonPlusSerializer(allowed_msgpack_modules=allowed)

    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        return SqliteSaver(conn, serde=serde)
    except sqlite3.Error:
        return MemorySaver(serde=serde)


def build_graph(checkpointer=None):
    builder = StateGraph(CloudCleanerState)

    builder.add_node("detect", detect_node)
    builder.add_node("investigate", investigate_node)
    builder.add_node("assess", assess_node)
    builder.add_node("policy_check", policy_check_node)
    builder.add_node("plan", plan_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)
    builder.add_node("verify", verify_node)
    builder.add_node("rollback", rollback_node)
    builder.add_node("record", record_node)

    builder.add_edge(START, "detect")
    builder.add_conditional_edges(
        "detect", route_after_detect, {"investigate": "investigate", "end": END}
    )
    builder.add_edge("investigate", "assess")
    builder.add_conditional_edges(
        "assess", route_after_assess,
        {"plan": "plan", "policy_check": "policy_check", "record": "record"}
    )
    builder.add_conditional_edges(
        "plan", route_after_plan, {"policy_check": "policy_check", "record": "record"}
    )
    builder.add_conditional_edges(
        "policy_check", route_after_policy_check,
        {"approval": "approval", "execute": "execute", "record": "record"},
    )
    builder.add_conditional_edges(
        "approval", route_after_approval,
        {"approval": "approval", "execute": "execute", "record": "record"},
    )
    builder.add_edge("execute", "verify")
    builder.add_conditional_edges(
        "verify", route_after_verify, {"complete": "record", "rollback": "rollback"}
    )
    builder.add_edge("rollback", "record")
    builder.add_edge("record", END)

    return builder.compile(checkpointer=checkpointer or _default_checkpointer())


graph = build_graph()