"""Run history and per-resource memory, backed by SQLite (storage/db.py).

Public API is unchanged from the JSONL version: record_run, list_runs, totals.
Added: recall() and recall_many(), which give the agent what it already knows
about a resource before it judges it again.
"""

import json
import uuid
from pathlib import Path

from cloudcleaner.storage.db import connect, now, rows_to_dicts

RUN_JSON_FIELDS = ("blocked", "actions")


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
        "at": now(),
        "dry_run": bool(dry_run),
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

    with connect(path) as conn:
        conn.execute(
            """INSERT INTO runs (run_id, at, dry_run, resource_id, resource_type,
                   resource_name, monthly_cost, verdict, severity, confidence, reason,
                   planned_steps, blocked, monthly_saving, decision, approved_by,
                   executed, actions, verified)
               VALUES (:run_id, :at, :dry_run, :resource_id, :resource_type,
                   :resource_name, :monthly_cost, :verdict, :severity, :confidence, :reason,
                   :planned_steps, :blocked, :monthly_saving, :decision, :approved_by,
                   :executed, :actions, :verified)""",
            {**run, "blocked": json.dumps(run["blocked"]), "actions": json.dumps(actions)},
        )
        _remember(conn, run)

        if plan and plan.restore and run["executed"]:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (run_id, resource_id, at, recipe) "
                "VALUES (?, ?, ?, ?)",
                (run["run_id"], run["resource_id"], run["at"], plan.restore.model_dump_json()),
            )

    return run


def _remember(conn, run: dict) -> None:
    """Fold this run into the resource's standing record."""
    kept = 1 if run["decision"] == "keep" or run["verdict"] == "keep" else 0
    retired_at = run["at"] if run["executed"] and not run["dry_run"] else None

    conn.execute(
        """INSERT INTO decisions (resource_id, last_seen_at, last_verdict, last_reason,
               human_decision, human_decided_at, times_seen, times_kept, retired_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
           ON CONFLICT(resource_id) DO UPDATE SET
               last_seen_at     = excluded.last_seen_at,
               last_verdict     = excluded.last_verdict,
               last_reason      = excluded.last_reason,
               human_decision   = COALESCE(excluded.human_decision, decisions.human_decision),
               human_decided_at = COALESCE(excluded.human_decided_at, decisions.human_decided_at),
               times_seen       = decisions.times_seen + 1,
               times_kept       = decisions.times_kept + excluded.times_kept,
               retired_at       = COALESCE(excluded.retired_at, decisions.retired_at)""",
        (
            run["resource_id"], run["at"], run["verdict"], run["reason"],
            run["decision"], run["at"] if run["decision"] else None,
            kept, retired_at,
        ),
    )


def recall(resource_id: str, path: Path | None = None) -> dict | None:
    """What the agent already knows about this resource. None on first sight."""
    with connect(path) as conn:
        row = conn.execute(
            "SELECT * FROM decisions WHERE resource_id = ?", (resource_id,)
        ).fetchone()
    return dict(row) if row else None


def recall_many(resource_ids: list[str], path: Path | None = None) -> dict[str, dict]:
    if not resource_ids:
        return {}
    placeholders = ",".join("?" * len(resource_ids))
    with connect(path) as conn:
        rows = conn.execute(
            f"SELECT * FROM decisions WHERE resource_id IN ({placeholders})", resource_ids
        ).fetchall()
    return {r["resource_id"]: dict(r) for r in rows}


def list_runs(limit: int = 100, path: Path | None = None) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY at DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows_to_dicts(rows, RUN_JSON_FIELDS)


def runs_for(resource_id: str, limit: int = 20, path: Path | None = None) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE resource_id = ? ORDER BY at DESC LIMIT ?",
            (resource_id, limit),
        ).fetchall()
    return rows_to_dicts(rows, RUN_JSON_FIELDS)


def restore_recipe(resource_id: str, path: Path | None = None) -> dict | None:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT recipe FROM snapshots WHERE resource_id = ? ORDER BY at DESC LIMIT 1",
            (resource_id,),
        ).fetchone()
    return json.loads(row["recipe"]) if row else None


def totals(path: Path | None = None) -> dict:
    with connect(path) as conn:
        r = conn.execute(
            """SELECT
                   COUNT(*)                                              AS runs,
                   SUM(decision = 'approve')                             AS approved,
                   SUM(verdict = 'keep' OR decision = 'keep')            AS kept,
                   SUM(blocked != '[]')                                  AS blocked,
                   COALESCE(SUM(CASE WHEN decision = 'approve' AND executed > 0
                                     AND dry_run = 0 THEN monthly_saving END), 0) AS realised,
                   COALESCE(SUM(CASE WHEN decision = 'approve' AND executed > 0
                                     AND dry_run = 1 THEN monthly_saving END), 0) AS simulated
               FROM runs"""
        ).fetchone()

    return {
        "runs": r["runs"] or 0,
        "approved": r["approved"] or 0,
        "kept": r["kept"] or 0,
        "blocked": r["blocked"] or 0,
        "realised_monthly": round(r["realised"] or 0, 2),
        "simulated_monthly": round(r["simulated"] or 0, 2),
    }
