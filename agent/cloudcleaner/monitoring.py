"""Continuous monitoring cycle for CloudCleaner."""

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
import uuid

from cloudcleaner.graph.graph import graph
from cloudcleaner.storage.repository import events_for
from cloudcleaner.tools.slack.messages import send_approval_request


_STATE_PATH = Path(__file__).resolve().parents[2] / "output" / "monitoring.json"
_RUN_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_state(path: Path = _STATE_PATH) -> dict:
    if not path.exists():
        return {
            "last_started_at": None,
            "last_completed_at": None,
            "last_error": None,
            "last_result": None,
            "resources": {},
        }

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "last_started_at": None,
            "last_completed_at": None,
            "last_error": None,
            "last_result": None,
            "resources": {},
        }

    data.setdefault("resources", {})
    data.setdefault("last_started_at", None)
    data.setdefault("last_completed_at", None)
    data.setdefault("last_error", None)
    data.setdefault("last_result", None)
    return data


def _save_state(state: dict, path: Path = _STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def monitoring_status(path: Path = _STATE_PATH) -> dict:
    state = _load_state(path)
    return {
        "last_started_at": state["last_started_at"],
        "last_completed_at": state["last_completed_at"],
        "last_error": state["last_error"],
        "last_result": state["last_result"],
    }


def cached_monitor_thread_id(
    resource_id: str,
    path: Path = _STATE_PATH,
) -> str | None:
    state = _load_state(path)
    resource_state = state["resources"].get(resource_id) or {}
    return resource_state.get("cached_thread_id")


def _resource_fingerprint(resource) -> str:
    payload = {
        "resource_id": resource.resource_id,
        "resource_type": resource.resource_type,
        "region": resource.region,
        "state": resource.state,
        "instance_type": resource.instance_type,
        "attached_to": resource.attached_to,
        "delete_on_termination": resource.delete_on_termination,
        "volume_ids": list(resource.volume_ids or []),
        "public_ip": resource.public_ip,
        "estimated_monthly_cost": resource.estimated_monthly_cost,
        "monthly_cost_if_stopped": resource.monthly_cost_if_stopped,
        "monthly_saving_if_stopped": resource.monthly_saving_if_stopped,
        "billing_while_stopped": resource.billing_while_stopped,
        "tags": resource.tags or {},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _notification_key(resource, recommendation, plan) -> str:
    steps = []
    if plan:
        steps = [
            {
                "action": step.action,
                "resource_id": step.resource_id,
                "depends_on": list(step.depends_on),
            }
            for step in plan.steps
        ]

    payload = {
        "resource_id": resource.resource_id,
        "resource_state": resource.state,
        "action": recommendation.action if recommendation else None,
        "blocked": list(plan.blocked) if plan else [],
        "steps": steps,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _reassessment_due(previous: dict, reassess_minutes: float) -> bool:
    if reassess_minutes <= 0:
        return False

    last_evaluated_at = _parse_time(previous.get("last_evaluated_at"))
    if last_evaluated_at is None:
        return True

    return datetime.now(timezone.utc) - last_evaluated_at >= timedelta(
        minutes=reassess_minutes
    )


def run_monitor_cycle(
    scan: dict,
    owner_email_resolver: Callable,
    reassess_minutes: float = 60,
    path: Path = _STATE_PATH,
) -> dict:
    if not _RUN_LOCK.acquire(blocking=False):
        return {
            "status": "busy",
            "message": "a monitoring cycle is already running",
        }

    state = _load_state(path)
    started_at = _now()
    state["last_started_at"] = started_at
    state["last_error"] = None
    _save_state(state, path)

    try:
        candidates = (scan.get("inventory") or []) + (scan.get("orphans") or [])
        current_ids = {resource.resource_id for resource in candidates}
        rows = []
        actionable = 0
        new_or_changed = 0
        agent_evaluations = 0
        notifications_sent = 0
        recoverable = 0.0

        for resource in candidates:
            previous = state["resources"].get(resource.resource_id, {})
            resource_fingerprint = _resource_fingerprint(resource)
            resource_changed = (
                previous.get("resource_fingerprint") != resource_fingerprint
            )
            due = _reassessment_due(previous, reassess_minutes)
            should_evaluate = resource_changed or due

            if not should_evaluate:
                rows.append(
                    {
                        "run_id": previous.get("last_run_id"),
                        "resource_id": resource.resource_id,
                        "action": previous.get("last_action"),
                        "severity": previous.get("last_severity"),
                        "confidence": previous.get("last_confidence"),
                        "reason": previous.get("last_reason"),
                        "blocked": previous.get("last_blocked", []),
                        "monthly_saving": previous.get("last_monthly_saving", 0.0),
                        "resource_changed": False,
                        "agent_evaluated": False,
                        "notification_sent": False,
                        "approval_thread_id": None,
                        "reasoning": [],
                    }
                )
                state["resources"][resource.resource_id]["last_seen_at"] = started_at
                recoverable += float(previous.get("last_monthly_saving") or 0.0)
                if previous.get("last_action") in ("stop", "retire") and not previous.get(
                    "last_blocked"
                ):
                    actionable += 1
                continue

            new_or_changed += 1
            agent_evaluations += 1

            analysis_thread_id = f"monitor-analysis-{resource.resource_id}-{uuid.uuid4()}"
            analysis_config = {"configurable": {"thread_id": analysis_thread_id}}
            result = graph.invoke(
                {**scan, "resource": resource, "analysis_only": True},
                analysis_config,
            )

            recommendation = result.get("recommendation")
            plan = result.get("plan")

            if recommendation and recommendation.action == "stop":
                saving = resource.monthly_saving_if_stopped or 0.0
            elif (
                recommendation
                and recommendation.action == "retire"
                and plan
                and plan.steps
                and not plan.blocked
            ):
                saving = sum(step.monthly_saving for step in plan.steps)
            else:
                saving = 0.0

            recoverable += saving

            is_actionable = bool(
                recommendation
                and recommendation.action in ("stop", "retire")
                and not (plan and plan.blocked)
            )
            if is_actionable:
                actionable += 1

            notification_key = _notification_key(resource, recommendation, plan)
            finding_changed = (
                previous.get("notification_key") != notification_key
            )
            notified = False
            approval_thread_id = None

            if is_actionable and finding_changed:
                approval_thread_id = str(uuid.uuid4())
                approval_config = {"configurable": {"thread_id": approval_thread_id}}
                approval_result = graph.invoke(
                    {**scan, "resource": resource},
                    approval_config,
                )
                pending = approval_result.get("__interrupt__")

                if pending:
                    send_approval_request(
                        approval_thread_id,
                        pending[0].value,
                        owner_email=owner_email_resolver(resource),
                    )
                    notifications_sent += 1
                    notified = True

            state["resources"][resource.resource_id] = {
                "last_seen_at": started_at,
                "last_evaluated_at": started_at,
                "resource_fingerprint": resource_fingerprint,
                "notification_key": notification_key,
                "last_action": recommendation.action if recommendation else None,
                "last_severity": recommendation.severity if recommendation else None,
                "last_confidence": recommendation.confidence if recommendation else None,
                "last_reason": recommendation.reason if recommendation else None,
                "last_blocked": plan.blocked if plan else [],
                "last_monthly_saving": round(saving, 2),
                "last_run_id": result.get("run_id"),
                "cached_thread_id": approval_thread_id or analysis_thread_id,
                "last_approval_thread_id": (
                    approval_thread_id
                    if notified
                    else previous.get("last_approval_thread_id")
                ),
                "last_notified_at": (
                    started_at
                    if notified
                    else previous.get("last_notified_at")
                ),
            }

            rows.append(
                {
                    "run_id": result.get("run_id"),
                    "resource_id": resource.resource_id,
                    "action": recommendation.action if recommendation else None,
                    "severity": recommendation.severity if recommendation else None,
                    "confidence": recommendation.confidence if recommendation else None,
                    "reason": recommendation.reason if recommendation else None,
                    "blocked": plan.blocked if plan else [],
                    "monthly_saving": round(saving, 2),
                    "resource_changed": resource_changed,
                    "agent_evaluated": True,
                    "notification_sent": notified,
                    "approval_thread_id": approval_thread_id if notified else None,
                    "reasoning": (
                        events_for(result["run_id"])
                        if result.get("run_id")
                        else []
                    ),
                }
            )

        missing_ids = set(state["resources"]) - current_ids
        for resource_id in missing_ids:
            state["resources"].pop(resource_id, None)

        result_summary = {
            "status": "completed",
            "started_at": started_at,
            "completed_at": _now(),
            "resources_checked": len(candidates),
            "new_or_changed": new_or_changed,
            "agent_evaluations": agent_evaluations,
            "actionable": actionable,
            "notifications_sent": notifications_sent,
            "recoverable_monthly": round(recoverable, 2),
            "recoverable_yearly": round(recoverable * 12, 2),
            "results": rows,
        }

        state["last_completed_at"] = result_summary["completed_at"]
        state["last_result"] = {
            key: value
            for key, value in result_summary.items()
            if key != "results"
        }
        _save_state(state, path)
        return result_summary

    except Exception as exc:
        state["last_error"] = str(exc)
        state["last_completed_at"] = _now()
        _save_state(state, path)
        raise
    finally:
        _RUN_LOCK.release()
