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
            "monthly_cost_if_stopped": resource.monthly_cost_if_stopped,
            "monthly_saving_if_stopped": resource.monthly_saving_if_stopped,
            "billing_while_stopped": resource.billing_while_stopped,
        },
        "recommendation": {
            "action": recommendation.action,
            "reason": recommendation.reason,
            "confidence": recommendation.confidence,
            "severity": recommendation.severity,
            "estimated_monthly_saving": recommendation.estimated_monthly_saving,
        },
        "plan": {
            "steps": [s.model_dump() for s in plan.steps],
            "total_monthly_saving": plan.total_monthly_saving,
            "irreversible_count": len(plan.irreversible_steps),
            "restore": plan.restore.model_dump() if plan.restore else None,
        } if plan else None,
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
    answer = interrupt(approval_payload(resource, state["recommendation"], plan))

    if isinstance(answer, dict) and answer.get("decision") == "reject":
        approved_by = answer.get("approved_by") or "ui"
        log.emit("approval", "decision", rid, f"rejected by {approved_by}")
        return {"approval": ApprovalDecision(
            decision="reject", approved_by=approved_by, reason="Rejected by human"),
            "approval_rounds": rounds}

    raw = answer if isinstance(answer, str) else (answer or {}).get("command", "")
    approved_by = (answer or {}).get("approved_by", "ui") if isinstance(answer, dict) else "cli"

    result = parse_approval(raw or "", rid)
    if not result["valid"]:
        log.emit("approval", "decision", rid, f"invalid approval response: {result['error']}")
        return {"approval": ApprovalDecision(
            decision="invalid", reason=result["error"]),
            "approval_rounds": rounds}

    log.emit("approval", "decision", rid, "approved by human")
    return {"approval": ApprovalDecision(
        decision="approve", approved_resource_ids=[rid], approved_by=approved_by),
        "approval_rounds": rounds}