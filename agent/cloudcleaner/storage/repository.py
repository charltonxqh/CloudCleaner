"""Append-only run history. JSONL so a partial write loses one line, not the file."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cloudcleaner.config import PROJECT_ROOT

HISTORY_PATH = PROJECT_ROOT / "output" / "history.jsonl"
RESTORE_DIR = PROJECT_ROOT / "output" / "restore"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_run(
    resource,
    recommendation=None,
    plan=None,
    approval=None,
    action_results=None,
    verification_passed=None,
    dry_run=True,
    path: Path | None = None,
) -> dict:
    actions = action_results or []
    executed = [a for a in actions if a.get("ok")]

    run = {
        "run_id": str(uuid.uuid4()),
        "at": _now(),
        "dry_run": dry_run,
        "resource_id": resource.resource_id,
        "resource_type": resource.resource_type,
        "resource_name": resource.name,
        "monthly_cost": resource.estimated_monthly_cost,
        "verdict": recommendation.action if recommendation else None,
        "severity": recommendation.severity if recommendation else None,
        "confidence": recommendation.confidence if recommendation else None,
        "reason": recommendation.reason if recommendation else None,
        "planned_steps": len(plan.steps) if plan else 0,
        "blocked": plan.blocked if plan else [],
        "monthly_saving": plan.total_monthly_saving if plan else 0.0,
        "decision": approval.decision if approval else None,
        "approved_by": approval.approved_by if approval else None,
        "executed": len(executed),
        "actions": actions,
        "verified": verification_passed,
    }

    target = path or HISTORY_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as f:
            f.write(json.dumps(run) + "\n")
    except OSError:
        pass

    if plan and plan.restore and run["executed"]:
        save_restore_recipe(run["run_id"], plan.restore)

    return run


def save_restore_recipe(run_id: str, restore, directory: Path | None = None) -> Path | None:
    target = (directory or RESTORE_DIR) / f"{run_id}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(restore.model_dump_json(indent=2))
        return target
    except OSError:
        return None


def list_runs(limit: int = 100, path: Path | None = None) -> list[dict]:
    target = path or HISTORY_PATH
    if not target.exists():
        return []

    runs = []
    for line in target.read_text().splitlines():
        if not line.strip():
            continue
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return list(reversed(runs))[:limit]


def totals(path: Path | None = None) -> dict:
    runs = list_runs(limit=10_000, path=path)
    realised = [r for r in runs if r["decision"] == "approve" and r["executed"] and not r["dry_run"]]
    simulated = [r for r in runs if r["decision"] == "approve" and r["executed"] and r["dry_run"]]

    return {
        "runs": len(runs),
        "approved": len([r for r in runs if r["decision"] == "approve"]),
        "kept": len([r for r in runs if r["verdict"] == "keep" or r["decision"] == "keep"]),
        "blocked": len([r for r in runs if r["blocked"]]),
        "realised_monthly": round(sum(r["monthly_saving"] for r in realised), 2),
        "simulated_monthly": round(sum(r["monthly_saving"] for r in simulated), 2),
    }
