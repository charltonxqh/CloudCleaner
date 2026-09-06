"""FastAPI surface. Lives in the package so `cloudcleaner serve` works from
an installed copy, not just from a checkout."""

import os
import uuid
import warnings
from pathlib import Path

from dotenv import load_dotenv

# config discovers .env on import; nothing to load by hand here
import cloudcleaner.config  # noqa: F401

import uvicorn
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from langgraph.types import Command
from pydantic import BaseModel

from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.graph import graph
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.storage.repository import (
    evaluation_metrics,
    event_stats,
    events_for,
    list_runs,
    runs_for,
    totals,
)
from cloudcleaner.tools.email.messages import send_owner_notification
from cloudcleaner.tools.slack.approvals import parse_interaction, verify_slack_signature
from cloudcleaner.tools.slack.messages import (
    send_approval_request,
    send_notification_status,
    update_approval_message,
)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_scans: dict[str, dict] = {}


def _scan(refresh: bool = False):
    if refresh or "latest" not in _scans:
        _scans["latest"] = detect_node({})
    return _scans["latest"]


def _owner_email(resource) -> str | None:
    if resource is None:
        return None

    tags = resource.tags or {}
    return (
        tags.get("OwnerEmail")
        or tags.get("owner_email")
        or os.getenv("CLOUDCLEANER_DEFAULT_OWNER_EMAIL")
    )


def _find_resource(resource_id: str):
    scan = _scan()
    pool = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    return next((r for r in pool if r.resource_id == resource_id), None)


def _resume_slack_approval(interaction: dict):
    config = {"configurable": {"thread_id": interaction["thread_id"]}}
    resume = {
        "decision": interaction["decision"],
        "command": f"APPROVE {interaction['resource_id']}" if interaction["decision"] == "approve" else "",
        "approved_by": interaction["approved_by"],
    }

    try:
        result = graph.invoke(Command(resume=resume), config)
        approval = result.get("approval")
        decision = approval.decision if approval else None
        status = "approved" if decision == "approve" else "rejected"
        text = (
            f"*CloudCleaner {status}* for `{interaction['resource_id']}` "
            f"by <@{interaction['approved_by'].split(':', 1)[-1]}>."
        )
    except Exception as e:
        text = f"*CloudCleaner approval failed* for `{interaction['resource_id']}`: {e}"

    if interaction.get("channel_id") and interaction.get("message_ts"):
        try:
            update_approval_message(interaction["channel_id"], interaction["message_ts"], text)
        except Exception:
            pass


def _email_slack_owner(interaction: dict):
    resource_id = interaction["resource_id"]
    config = {"configurable": {"thread_id": interaction["thread_id"]}}

    try:
        resource = _find_resource(resource_id)
        if resource is None:
            raise RuntimeError(f"resource {resource_id} is no longer available")

        owner_email = _owner_email(resource)
        if not owner_email:
            raise RuntimeError("owner email is not configured")

        snapshot = graph.get_state(config)
        state = snapshot.values

        recommendation = state.get("recommendation")
        plan = state.get("plan")

        if recommendation is None:
            raise RuntimeError("recommendation is not available for this approval")

        response = send_owner_notification(
            to_email=owner_email,
            resource=resource,
            recommendation=recommendation,
            plan=plan,
        )

        message_id = response.get("MessageId")
        log.emit(
            "notify",
            "decision",
            resource_id,
            f"owner notified by email: {owner_email}",
        )

        text = f"✉️ Owner notification sent to `{owner_email}`."
        if message_id:
            text += f" SES message ID: `{message_id}`"

    except Exception as e:
        log.emit(
            "notify",
            "error",
            resource_id,
            f"owner email failed: {e}",
        )
        text = f"⚠️ CloudCleaner could not email the owner: {e}"

    if interaction.get("channel_id") and interaction.get("message_ts"):
        try:
            send_notification_status(
                interaction["channel_id"],
                interaction["message_ts"],
                text,
            )
        except Exception:
            pass


def _dump_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _thread_status(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}

    try:
        snapshot = graph.get_state(config)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"unknown thread {thread_id}") from e

    state = snapshot.values or {}
    if not state:
        raise HTTPException(status_code=404, detail=f"unknown thread {thread_id}")

    resource = state.get("resource")
    resource_id = resource.resource_id if resource else None
    approval = state.get("approval")
    run_id = state.get("run_id")

    tasks = getattr(snapshot, "tasks", ()) or ()
    awaiting_approval = any(
        bool(getattr(task, "interrupts", ()))
        for task in tasks
    )

    if awaiting_approval:
        phase = "awaiting_approval"
    elif state.get("error"):
        phase = "error"
    elif run_id:
        phase = "completed"
    else:
        phase = "running"

    if run_id:
        reasoning = events_for(run_id)
    else:
        reasoning = [
            event
            for event in log.events
            if resource_id is None or event.get("resource_id") in (resource_id, "-")
        ]

    return {
        "thread_id": thread_id,
        "resource_id": resource_id,
        "phase": phase,
        "awaiting_approval": awaiting_approval,
        "run_id": run_id,
        "decision": approval.decision if approval else None,
        "approved_by": approval.approved_by if approval else None,
        "reason": approval.reason if approval else None,
        "recommendation": _dump_model(state.get("recommendation")),
        "plan": _dump_model(state.get("plan")),
        "action_results": state.get("action_results") or [],
        "verification_passed": state.get("verification_passed"),
        "reasoning": reasoning,
        "error": state.get("error"),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


class InvestigateRequest(BaseModel):
    resource_id: str
    force_plan: bool = False


class ApproveRequest(BaseModel):
    thread_id: str
    command: str


@app.get("/inventory")
async def inventory(refresh: bool = False):
    scan = _scan(refresh)
    resources = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    return {
        "resources": [r.model_dump() for r in resources],
        "total_monthly": round(sum(r.estimated_monthly_cost or 0 for r in resources), 2),
        "wasting": [r.resource_id for r in resources if r.billing_while_stopped],
    }


@app.post("/investigate")
async def investigate(req: InvestigateRequest):
    scan = _scan()
    pool = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    resource = next((r for r in pool if r.resource_id == req.resource_id), None)
    if resource is None:
        return {"error": f"unknown resource {req.resource_id}"}

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {**scan, "resource": resource, "force_plan": req.force_plan}, config
    )

    rec = result.get("recommendation")
    plan = result.get("plan")
    pending = result.get("__interrupt__")

    if pending:
        try:
            send_approval_request(
                thread_id,
                pending[0].value,
                owner_email=_owner_email(resource),
            )
        except Exception as e:
            log.emit("approval", "error", resource.resource_id, f"Slack approval message failed: {e}")

    return {
        "thread_id": thread_id,
        "resource": resource.model_dump(),
        "evidence": result["aws_evidence"].model_dump() if result.get("aws_evidence") else None,
        "github": result["github_evidence"].model_dump() if result.get("github_evidence") else None,
        "recommendation": rec.model_dump() if rec else None,
        "plan": plan.model_dump() if plan else None,
        "awaiting_approval": bool(pending),
        "approval_request": pending[0].value if pending else None,
        "reasoning": log.events,
    }


@app.get("/threads/{thread_id}/status")
async def thread_status(thread_id: str):
    """Current state of one investigation, including a paused Slack approval."""
    return _thread_status(thread_id)


@app.get("/history")
async def history(limit: int = 50):
    return {"runs": list_runs(limit), "totals": totals(), "stats": event_stats()}


@app.get("/evaluation")
async def evaluation():
    return evaluation_metrics()


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    """The reasoning that produced one recorded run."""
    return {"run_id": run_id, "events": events_for(run_id)}


@app.get("/resources/{resource_id}/runs")
async def resource_runs(resource_id: str, limit: int = 20):
    return {"resource_id": resource_id, "runs": runs_for(resource_id, limit)}


@app.post("/sweep")
async def sweep():
    """Assess every candidate without approving anything."""
    scan = _scan(refresh=True)
    candidates = (scan.get("inventory") or []) + (scan.get("orphans") or [])

    rows, recoverable = [], 0.0
    for resource in candidates:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke(
            {**scan, "resource": resource, "analysis_only": True}, config
        )

        rec = result.get("recommendation")
        plan = result.get("plan")
        if rec and rec.action == "stop":
            saving = resource.monthly_saving_if_stopped or 0.0
        elif rec and rec.action == "retire" and plan and plan.steps and not plan.blocked:
            saving = sum(s.monthly_saving for s in plan.steps)
        else:
            saving = 0.0
        recoverable += saving

        rows.append({
            "run_id": result.get("run_id"),
            "resource_id": resource.resource_id,
            "action": rec.action if rec else None,
            "severity": rec.severity if rec else None,
            "confidence": rec.confidence if rec else None,
            "reason": rec.reason if rec else None,
            "steps": len(plan.steps) if plan else 0,
            "blocked": plan.blocked if plan else [],
            "monthly_saving": round(saving, 2),
        })

    trail = [e for row in rows if row["run_id"] for e in events_for(row["run_id"])]

    return {
        "results": rows,
        "recoverable_monthly": round(recoverable, 2),
        "recoverable_yearly": round(recoverable * 12, 2),
        "reasoning": trail,
    }


@app.post("/approve")
async def approve(req: ApproveRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    result = graph.invoke(Command(resume=req.command), config)
    approval = result.get("approval")
    run_id = result.get("run_id")

    return {
        "decision": approval.decision if approval else None,
        "reason": approval.reason if approval else None,
        "action_results": result.get("action_results") or [],
        "verification_passed": result.get("verification_passed"),
        "run_id": run_id,
        # The run has been recorded by now, so its trail lives in the database
        # rather than the in-memory buffer.
        "reasoning": events_for(run_id) if run_id else [],
    }


@app.post("/slack/interactions")
async def slack_interactions(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    if not verify_slack_signature(request.headers, raw_body):
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    try:
        interaction = parse_interaction(raw_body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if interaction["action"] == "email_owner":
        background_tasks.add_task(_email_slack_owner, interaction)
    else:
        background_tasks.add_task(_resume_slack_approval, interaction)

    return {"ok": True}


add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="cloudcleaner",
        description="Investigates idle AWS resources and plans a dependency-ordered teardown.",
        graph=graph,
    ),
    path="/",
)


def main():
    uvicorn.run("cloudcleaner.server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8123")), reload=True)


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

if __name__ == "__main__":
    main()