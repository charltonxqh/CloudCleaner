import os

os.environ.setdefault("CLOUDCLEANER_PROVIDER", "fixture")
os.environ.setdefault("CLOUDCLEANER_AI_ENABLED", "false")

import pytest

from cloudcleaner.fixtures import demo
from cloudcleaner.graph.routing import (
    route_after_assess,
    route_after_detect,
    route_after_plan,
    route_after_approval,
)
from cloudcleaner.schemas import ApprovalDecision, Recommendation, TeardownPlan, TeardownStep


def _rec(action):
    return Recommendation(action=action, reason="t", confidence=0.9)


def test_empty_account_ends_cleanly_and_is_not_an_error():
    assert route_after_detect({"done_reason": "nothing to investigate"}) == "end"


@pytest.mark.parametrize("action,expected", [
    ("keep", "record"),
    ("investigate_more", "record"),
    # a stop is a single Action, so it goes to the policy gate first;
    # a retirement is multi-step, so it is planned before the gate sees it
    ("stop", "policy_check"),
    ("retire", "plan"),
])
def test_only_actionable_verdicts_reach_the_planner(action, expected):
    assert route_after_assess({"recommendation": _rec(action)}) == expected


def test_blocked_plan_never_reaches_approval():
    plan = TeardownPlan(root_resource_id="i-1", blocked=["Environment=prod is protected"])
    assert route_after_plan({"plan": plan}) == "record"


def test_empty_plan_never_reaches_approval():
    assert route_after_plan({"plan": TeardownPlan(root_resource_id="i-1")}) == "record"


def test_unapproved_plan_never_executes():
    assert route_after_approval({"approval": ApprovalDecision(decision="reject")}) == "record"


def test_approved_plan_executes():
    approval = ApprovalDecision(decision="approve", approved_resource_ids=["i-1"])
    # approval_rounds must satisfy policy_result.required_approvals (default 1),
    # otherwise routing loops back for another round.
    assert route_after_approval({"approval": approval, "approval_rounds": 1}) == "execute"


def test_fixture_sweep_finds_the_idle_stack_and_spares_prod():
    import uuid

    from cloudcleaner.graph.graph import graph
    from cloudcleaner.graph.nodes.detect import detect_node

    scan = detect_node({})
    verdicts = {}
    for resource in (scan["inventory"] + scan["orphans"]):
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke({**scan, "resource": resource}, config)
        verdicts[resource.resource_id] = result["recommendation"].action

    assert verdicts["i-0999prod888"] == "keep"
    assert verdicts["i-0abc123def456789"] == "retire"
    assert verdicts["vol-0orphan11"] == "retire"
    assert verdicts["eipalloc-0unused9"] == "retire"


def test_prod_is_blocked_by_policy_even_if_the_model_says_retire():
    from cloudcleaner.graph.nodes.plan import plan_node

    prod = demo.list_ec2_instances()[1]
    plan = plan_node({"resource": prod, "volumes": demo.list_volumes(),
                      "addresses": demo.list_elastic_ips()})["plan"]

    assert plan.blocked
    assert not plan.steps


def test_teardown_for_the_idle_instance_covers_its_entanglement():
    from cloudcleaner.graph.nodes.plan import plan_node

    instance = demo.list_ec2_instances()[0]
    plan = plan_node({
        "resource": instance,
        "volumes": demo.list_volumes(),
        "addresses": demo.list_elastic_ips(),
    })["plan"]

    assert [s.action for s in plan.steps] == [
        "disassociate_address", "release_address", "snapshot_volume",
        "terminate_instance", "delete_volume",
    ]
    assert plan.total_monthly_saving > 0
    assert plan.restore is not None


def test_approval_interrupt_pauses_and_resumes():
    import uuid

    from langgraph.types import Command

    from cloudcleaner.graph.graph import graph
    from cloudcleaner.graph.nodes.detect import detect_node

    scan = detect_node({})
    target = next(r for r in scan["orphans"] if r.resource_id == "eipalloc-0unused9")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    paused = graph.invoke({**scan, "resource": target}, config)
    payload = paused["__interrupt__"][0].value
    assert payload["expected_command"] == "APPROVE eipalloc-0unused9"
    assert payload["plan"]["total_monthly_saving"] > 0

    refused = graph.invoke(Command(resume="y"), config)
    assert refused["approval"].decision == "invalid"
    assert not refused.get("action_results")


def test_approval_interrupt_executes_on_exact_command():
    import uuid

    from langgraph.types import Command

    from cloudcleaner.graph.graph import graph
    from cloudcleaner.graph.nodes.detect import detect_node

    scan = detect_node({})
    target = next(r for r in scan["orphans"] if r.resource_id == "eipalloc-0unused9")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph.invoke({**scan, "resource": target}, config)
    done = graph.invoke(Command(resume="APPROVE eipalloc-0unused9"), config)

    assert done["approval"].decision == "approve"
    assert done["action_results"][0]["action"] == "release_address"
    assert done["action_results"][0]["dry_run"] is True


def test_every_terminal_path_is_recorded():
    """A resource that was looked at must leave a trace, whatever the outcome."""
    from cloudcleaner.graph.routing import route_after_assess, route_after_plan, route_after_approval

    assert route_after_assess({"recommendation": _rec("keep")}) == "record"
    assert route_after_plan({"plan": TeardownPlan(root_resource_id="i-1", blocked=["x"])}) == "record"
    assert route_after_approval({"approval": ApprovalDecision(decision="reject")}) == "record"
