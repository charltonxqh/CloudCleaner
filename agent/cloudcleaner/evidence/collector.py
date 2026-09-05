"""Reasoning trail.

Every event is buffered for the current run, appended to a JSONL file for
tailing, and flushed to SQLite when the run is recorded. The buffer is scoped
to a run rather than the process, so one investigation never reports another's
reasoning.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cloudcleaner.config import DATA_DIR

EVENT_TYPES = {"check", "finding", "skip", "decision", "action", "handoff", "error"}
CORE_FIELDS = ("ts", "node", "event", "resource_id", "message")
DEFAULT_LOG = DATA_DIR / "reasoning.jsonl"


class ReasoningLog:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_LOG
        self.events: list[dict] = []

    def start(self, truncate_file: bool = False):
        """Begin a new run. The file is appended to unless asked to truncate."""
        self.events = []
        if not truncate_file:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")
        except OSError as e:
            print(f"[reasoning] cannot open log: {e}", file=sys.stderr)

    def emit(self, node: str, event: str, resource_id: str, message: str, **extra):
        if event not in EVENT_TYPES:
            event = "check"
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "event": event,
            "resource_id": resource_id,
            "message": message,
            **extra,
        }
        self.events.append(record)

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"[reasoning] write failed: {e}", file=sys.stderr)

        return record

    def flush(self, run_id: str, conn) -> int:
        """Persist this run's events against the run that produced them."""
        if not self.events:
            return 0

        conn.executemany(
            """INSERT INTO events (run_id, at, node, event, resource_id, message, extra)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    run_id, e["ts"], e["node"], e["event"], e["resource_id"], e["message"],
                    json.dumps({k: v for k, v in e.items() if k not in CORE_FIELDS}),
                )
                for e in self.events
            ],
        )
        count = len(self.events)
        self.events = []
        return count


log = ReasoningLog()
