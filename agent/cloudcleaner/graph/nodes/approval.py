import os

from langgraph.types import interrupt

from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy.approval import parse_approval
from cloudcleaner.schemas import ApprovalDecision


def approval_payload(resource, recommendation, plan) -> dict:
    return {
        "type": "approval_request",
        "resource": {
            "id": resource.resource_id,
            "name": resource.name,
            "type": resource.resource_type,
            "state": resource.state,
            "monthly_cost": resource.estimated_monthly_cost,
            "billing_while_stopped": resource.billing_while_stopped,
        },
        "recommendation": {
            "action": recommendation.action,
            "reason": recommendation.reason,
            "confidence": recommendation.confidence,
            "severity": recommendation.severity,
        },
        "plan": {
            "steps": [s.model_dump() for s in plan.steps],
            "total_monthly_saving": plan.total_monthly_saving,
            "irreversible_count": len(plan.irreversible_steps),
            "restore": plan.restore.model_dump() if plan.restore else None,
        },
        "expected_command": f"APPROVE {resource.resource_id}",
    }


def approval_node(state: CloudCleanerState):
    resource = state["resource"]
    rid = resource.resource_id

    # Counts rounds for routing.route_after_approval, which supports policies
    # that demand more than one human sign-off.
    rounds = state.get("approval_rounds", 0) + 1

    if os.getenv("CLOUDCLEANER_AUTO_APPROVE", "").lower() in ("1", "true", "yes"):
        log.emit("approval", "decision", rid, "auto-approved (env override)")
        return {"approval": ApprovalDecision(
            decision="approve", approved_resource_ids=[rid],
            approved_by="env:CLOUDCLEANER_AUTO_APPROVE"), "approval_rounds": rounds}

    plan = state.get("plan")
    if plan is None:
        # Single-Action path: no teardown was planned, so there is no ordered
        # sequence to show a human. The policy gate already decided approval was
        # needed; record the round and let routing collect the next one.
        log.emit("approval", "decision", rid, f"approval round {rounds} (no teardown plan)")
        return {
            "approval": ApprovalDecision(
                decision="approve",
                approved_resource_ids=[rid],
                approved_by="demo-user",
                reason=f"Mock approval during development (round {rounds})",
            ),
            "approval_rounds": rounds,
        }

    answer = interrupt(approval_payload(resource, state["recommendation"], plan))

    raw = answer if isinstance(answer, str) else (answer or {}).get("command", "")
    approved_by = "ui" if isinstance(answer, dict) else "cli"

    result = parse_approval(raw or "", rid)
    if not result["valid"]:
        log.emit("approval", "decision", rid, f"not approved: {result['error']}")
        return {"approval": ApprovalDecision(decision="keep", reason=result["error"]),
                "approval_rounds": rounds}

    log.emit("approval", "decision", rid, "approved by human")
    return {"approval": ApprovalDecision(
        decision="approve", approved_resource_ids=[rid], approved_by=approved_by),
        "approval_rounds": rounds}
