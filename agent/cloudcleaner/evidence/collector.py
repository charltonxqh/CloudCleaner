import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cloudcleaner.config import DATA_DIR

EVENT_TYPES = {"check", "finding", "skip", "decision", "action", "handoff", "error"}
DEFAULT_LOG = DATA_DIR / "reasoning.jsonl"


class ReasoningLog:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_LOG
        self.events: list[dict] = []

    def start(self):
        self.events = []
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
            with self.path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"[reasoning] write failed: {e}", file=sys.stderr)
        return record


log = ReasoningLog()
