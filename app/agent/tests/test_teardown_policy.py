"""Teardown planning: dependency ordering, plan-time guardrails, approval gate."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cloudcleaner.policy import safety
from cloudcleaner.policy.approval import ApprovalGate, parse_approval
from cloudcleaner.policy.dependencies import DependencyCycle, order_steps, resolve
from cloudcleaner.schemas import CloudResource, TeardownStep


def _instance(**kw):
    base = dict(resource_id="i-1", resource_type="ec2", region="us-east-1",
                state="stopped", instance_type="t3.micro", estimated_monthly_cost=4.93,
                tags={"Name": "x"})
    return CloudResource(**{**base, **kw})


# --- dependency ordering -----------------------------------------------------

ids = st.text("abcdef0123456789", min_size=2, max_size=6)


@st.composite
def dag(draw):
    """A random set of steps whose depends_on edges only point at earlier steps."""
    n = draw(st.integers(min_value=1, max_value=12))
    steps = []
    for i in range(n):
        deps = draw(st.lists(st.integers(0, i - 1), max_size=min(i, 3), unique=True)) if i else []
        steps.append(TeardownStep(
            action="delete_volume",
            resource_id=f"r{i}",
            resource_type="ebs",
            reason="t",
            depends_on=[f"delete_volume:r{d}" for d in deps],
        ))
    return steps


@settings(max_examples=200)
@given(dag())
def test_ordering_never_places_a_step_before_its_dependency(steps):
    ordered = order_steps(steps)
    position = {f"{s.action}:{s.resource_id}": s.order for s in ordered}

    assert len(ordered) == len(steps)
    for step in ordered:
        for dep in step.depends_on:
            assert position[dep] < step.order


def test_cycle_is_rejected():
    a = TeardownStep(action="delete_volume", resource_id="a", resource_type="ebs",
                     reason="t", depends_on=["delete_volume:b"])
    b = TeardownStep(action="delete_volume", resource_id="b", resource_type="ebs",
                     reason="t", depends_on=["delete_volume:a"])
    with pytest.raises(DependencyCycle):
        order_steps([a, b])


def test_eip_is_disassociated_before_release():
    inst = _instance()
    eip = CloudResource(resource_id="eipalloc-1", resource_type="eip", region="us-east-1",
                        attached_to="i-1", estimated_monthly_cost=3.65,
                        tags={"AssociationId": "eipassoc-1"})
    steps = resolve(inst, [], [eip])
    order = {s.action: s.order for s in steps}
    assert order["disassociate_address"] < order["release_address"]


def test_volume_is_snapshotted_before_terminate_and_deleted_after():
    inst = _instance()
    vol = CloudResource(resource_id="vol-1", resource_type="ebs", region="us-east-1",
                        size_gb=16, attached_to="i-1", delete_on_termination=False,
                        estimated_monthly_cost=1.28)
    steps = resolve(inst, [vol], [])
    order = {s.action: s.order for s in steps}
    assert order["snapshot_volume"] < order["terminate_instance"] < order["delete_volume"]


def test_volume_that_aws_cleans_up_is_not_deleted_twice():
    inst = _instance()
    vol = CloudResource(resource_id="vol-1", resource_type="ebs", region="us-east-1",
                        size_gb=16, attached_to="i-1", delete_on_termination=True)
    actions = {s.action for s in resolve(inst, [vol], [])}
    assert "delete_volume" not in actions


# --- safety ------------------------------------------------------------------

@pytest.mark.parametrize("env", ["prod", "Production", "LIVE"])
def test_protected_environments_are_blocked(env):
    assert not safety.is_safe(_instance(environment=env))


def test_protected_tag_blocks():
    assert not safety.is_safe(_instance(tags={"DoNotDelete": "yes"}))


def test_young_resource_is_blocked():
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert not safety.is_safe(_instance(launch_time=recent))


def test_untagged_blocked_unless_allowed():
    r = _instance(tags={})
    assert not safety.is_safe(r)
    assert safety.is_safe(r, allow_untagged=True)


# --- approval ----------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "approve i-1", "APPROVE  i-1", " APPROVE i-1", "APPROVE i-1 ",
    "APPROVE", "APPROVE i-2", "y", "yes", "",
])
def test_approval_rejects_anything_but_exact_match(raw):
    assert parse_approval(raw, "i-1")["valid"] is False


def test_approval_accepts_exact_match():
    assert parse_approval("APPROVE i-1", "i-1")["valid"] is True


def test_gate_locks_after_three_failures():
    gate = ApprovalGate(max_attempts=3)
    for _ in range(3):
        gate.attempt("y", "i-1")
    assert gate.locked
    assert gate.attempt("APPROVE i-1", "i-1")["valid"] is False
