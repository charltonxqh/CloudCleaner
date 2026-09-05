"""Run history and per-resource memory, backed by SQLite (storage/db.py).

Public API is unchanged from the JSONL version: record_run, list_runs, totals.
Added: recall() and recall_many(), which give the agent what it already knows
about a resource before it judges it again.
"""

import json
import uuid
from pathlib import Path

from cloudcleaner.evidence.collector import log
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
        run["events"] = log.flush(run["run_id"], conn)

        if plan and plan.restore and run["executed"]:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (run_id, resource_id, at, recipe) "
                "VALUES (?, ?, ?, ?)",
                (run["run_id"], run["resource_id"], run["at"], plan.restore.model_dump_json()),
            )

    return run


def _remember(conn, run: dict) -> None:
    """Fold this run into the resource's standing record."""
    human_decision = run["decision"] if run["decision"] in ("approve", "reject") else None
    human_decided_at = run["at"] if human_decision else None
    human_decided_by = run["approved_by"] if human_decision else None
    retired_at = run["at"] if run["executed"] and not run["dry_run"] else None

    conn.execute(
        """INSERT INTO decisions (resource_id, last_seen_at, last_verdict, last_reason,
               human_decision, human_decided_at, human_decided_by, times_seen, retired_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
           ON CONFLICT(resource_id) DO UPDATE SET
               last_seen_at      = excluded.last_seen_at,
               last_verdict      = excluded.last_verdict,
               last_reason       = excluded.last_reason,
               human_decision    = COALESCE(excluded.human_decision, decisions.human_decision),
               human_decided_at  = COALESCE(excluded.human_decided_at, decisions.human_decided_at),
               human_decided_by  = COALESCE(excluded.human_decided_by, decisions.human_decided_by),
               times_seen        = decisions.times_seen + 1,
               retired_at        = COALESCE(excluded.retired_at, decisions.retired_at)""",
        (
            run["resource_id"], run["at"], run["verdict"], run["reason"],
            human_decision, human_decided_at, human_decided_by, retired_at,
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


def events_for(run_id: str, path: Path | None = None) -> list[dict]:
    """The reasoning that produced one run, oldest first."""
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()

    out = []
    for r in rows_to_dicts(rows, ("extra",)):
        extra = r.pop("extra", {}) or {}
        out.append({**r, **extra})
    return out


def event_stats(path: Path | None = None) -> dict:
    """Counts the deck needs: how often each node errors, skips or decides."""
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT node, event, COUNT(*) AS n FROM events GROUP BY node, event"
        ).fetchall()
        fallbacks = conn.execute(
            "SELECT COUNT(*) FROM events WHERE node = 'assess' AND event = 'error'"
        ).fetchone()[0]
        assessments = conn.execute(
            "SELECT COUNT(*) FROM events WHERE node = 'assess' AND event = 'decision'"
        ).fetchone()[0]

    by_node: dict[str, dict[str, int]] = {}
    for r in rows:
        by_node.setdefault(r["node"], {})[r["event"]] = r["n"]

    return {
        "by_node": by_node,
        "assessments": assessments,
        "llm_fallbacks": fallbacks,
        "llm_success_rate": round(1 - fallbacks / assessments, 3) if assessments else None,
    }


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
                   SUM(verdict = 'keep')                                 AS kept,
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


def evaluation_metrics(path: Path | None = None) -> dict:
    """Evaluation metrics that can be derived from the evidence already recorded.

    Recommendation accuracy still needs an independently labelled benchmark.
    Token cost still needs provider token-usage telemetry. Those are reported as
    unavailable rather than manufacturing a score from unrelated data.

    The remaining metrics use data CloudCleaner already persists:
    - tool-call success: instrumented investigate/execute/notify stages
    - teardown correctness: actionable retirement plans, plus complete execution
      and verification when an approved plan actually ran
    - savings accuracy: predicted saving against direct billed cost for independent
      EBS/EIP resources, where the reference amount is unambiguous
    """
    stats = event_stats(path)

    with connect(path) as conn:
        tool_rows = conn.execute(
            """SELECT node, event, COUNT(*) AS n
               FROM events
               WHERE node IN ('investigate', 'execute', 'notify')
               GROUP BY node, event"""
        ).fetchall()

        plan_rows = conn.execute(
            """SELECT planned_steps, blocked, decision, executed, verified
               FROM runs
               WHERE verdict = 'retire'"""
        ).fetchall()

        saving_rows = conn.execute(
            """SELECT resource_type, verdict, monthly_cost, monthly_saving
               FROM runs
               WHERE resource_type IN ('ebs', 'eip')
                 AND verdict IN ('retire', 'keep')
                 AND monthly_cost IS NOT NULL"""
        ).fetchall()

    tool_successes = 0
    tool_failures = 0
    successful_events = {
        ("investigate", "finding"),
        ("execute", "action"),
        ("notify", "decision"),
    }

    for row in tool_rows:
        key = (row["node"], row["event"])
        if row["event"] == "error":
            tool_failures += row["n"]
        elif key in successful_events:
            tool_successes += row["n"]

    tool_attempts = tool_successes + tool_failures
    tool_success_rate = (
        round(tool_successes / tool_attempts, 3) if tool_attempts else None
    )

    plan_samples = 0
    correct_plans = 0

    for row in plan_rows:
        try:
            blocked = json.loads(row["blocked"] or "[]")
        except (TypeError, json.JSONDecodeError):
            blocked = []

        if blocked:
            continue

        plan_samples += 1
        correct = row["planned_steps"] > 0

        if row["decision"] == "approve" and row["executed"] > 0:
            correct = (
                correct
                and row["executed"] == row["planned_steps"]
                and row["verified"] != 0
            )

        if correct:
            correct_plans += 1

    teardown_plan_correctness = (
        round(correct_plans / plan_samples, 3) if plan_samples else None
    )

    saving_scores: list[float] = []

    for row in saving_rows:
        reference = float(row["monthly_cost"] or 0.0)
        predicted = float(row["monthly_saving"] or 0.0)

        if row["verdict"] == "keep":
            reference = 0.0

        if reference == 0:
            score = 1.0 if predicted == 0 else 0.0
        else:
            score = max(0.0, 1 - abs(predicted - reference) / reference)

        saving_scores.append(score)

    savings_accuracy = (
        round(sum(saving_scores) / len(saving_scores), 3)
        if saving_scores
        else None
    )

    return {
        "recommendation_accuracy": None,
        "recommendation_samples": 0,
        "schema_validation_rate": stats["llm_success_rate"],
        "schema_validation_samples": stats["assessments"],
        "avg_token_cost_usd": None,
        "token_cost_samples": 0,
        "tool_call_success_rate": tool_success_rate,
        "tool_call_successes": tool_successes,
        "tool_call_attempts": tool_attempts,
        "teardown_plan_correctness": teardown_plan_correctness,
        "teardown_plan_correct": correct_plans,
        "teardown_plan_samples": plan_samples,
        "savings_accuracy": savings_accuracy,
        "savings_accuracy_samples": len(saving_scores),
    }