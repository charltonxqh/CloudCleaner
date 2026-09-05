import os
import uuid
import warnings
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import uvicorn
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langgraph.types import Command
from pydantic import BaseModel

from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.graph import graph
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.storage.repository import (
    event_stats,
    events_for,
    list_runs,
    runs_for,
    totals,
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


@app.get("/history")
async def history(limit: int = 50):
    return {"runs": list_runs(limit), "totals": totals(), "stats": event_stats()}


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
        result = graph.invoke({**scan, "resource": resource}, config)

        rec = result.get("recommendation")
        plan = result.get("plan")
        saving = sum(s.monthly_saving for s in plan.steps) if plan and plan.steps else 0.0
        recoverable += saving

        # A sweep assesses, it never approves. Close the thread so the run is
        # recorded as "not approved" instead of dangling at the interrupt.
        if result.get("__interrupt__"):
            result = graph.invoke(Command(resume=""), config)

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
        "decision": approval.decision if approval else "keep",
        "reason": approval.reason if approval else None,
        "action_results": result.get("action_results") or [],
        "verification_passed": result.get("verification_passed"),
        "run_id": run_id,
        # The run has been recorded by now, so its trail lives in the database
        # rather than the in-memory buffer.
        "reasoning": events_for(run_id) if run_id else [],
    }


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
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8123")), reload=True)


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

if __name__ == "__main__":
    main()
