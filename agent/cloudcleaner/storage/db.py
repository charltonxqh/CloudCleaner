"""SQLite store. Stdlib only — nothing for a teammate to install or run.

One file at output/cloudcleaner.db, three tables:

  runs        every completed investigation, whatever the outcome
  decisions   the latest state per resource — the agent's long-term memory
  snapshots   restore recipes, so a terminate stays recoverable
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cloudcleaner.config import DATA_DIR

DB_PATH = DATA_DIR / "cloudcleaner.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    at                TEXT NOT NULL,
    dry_run           INTEGER NOT NULL DEFAULT 1,
    resource_id       TEXT NOT NULL,
    resource_type     TEXT,
    resource_name     TEXT,
    monthly_cost      REAL,
    verdict           TEXT,
    severity          TEXT,
    confidence        REAL,
    reason            TEXT,
    planned_steps     INTEGER DEFAULT 0,
    blocked           TEXT DEFAULT '[]',
    monthly_saving    REAL DEFAULT 0,
    decision          TEXT,
    approved_by       TEXT,
    executed          INTEGER DEFAULT 0,
    actions           TEXT DEFAULT '[]',
    verified          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_runs_resource ON runs(resource_id);
CREATE INDEX IF NOT EXISTS idx_runs_at ON runs(at DESC);

-- One row per resource: what we last concluded and what the human last said.
CREATE TABLE IF NOT EXISTS decisions (
    resource_id       TEXT PRIMARY KEY,
    last_seen_at      TEXT NOT NULL,
    last_verdict      TEXT,
    last_reason       TEXT,
    human_decision    TEXT,
    human_decided_at  TEXT,
    human_decided_by  TEXT,
    times_seen        INTEGER DEFAULT 1,
    retired_at        TEXT
);

-- One row per logged decision. run_id is filled in when the run is recorded,
-- since the id does not exist until the graph reaches its terminal node.
CREATE TABLE IF NOT EXISTS events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT,
    at                TEXT NOT NULL,
    node              TEXT NOT NULL,
    event             TEXT NOT NULL,
    resource_id       TEXT,
    message           TEXT,
    extra             TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at DESC);

CREATE TABLE IF NOT EXISTS snapshots (
    run_id            TEXT PRIMARY KEY,
    resource_id       TEXT NOT NULL,
    at                TEXT NOT NULL,
    recipe            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_resource ON snapshots(resource_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    # Survives a crash mid-write and allows a reader while the agent writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def rows_to_dicts(rows, json_fields=()) -> list[dict]:
    out = []
    for r in rows:
        d = dict(r)
        for f in json_fields:
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
        out.append(d)
    return out