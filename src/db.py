"""
db.py
=====
Lightweight SQLite persistence for the triage workflow — the "closed loop".

The detector produces a prioritized queue; this layer lets an ops user record what
they *did* about a flagged customer (contacted, save-offer sent, dismissed, snoozed)
and persists it, so the queue shows live status and every decision is auditable.
This is the first concrete step of the "closed-loop learning" roadmap item: capture
intervention outcomes to later correlate against retention.

Pure standard-library sqlite3 (no extra dependency). Safe for concurrent Streamlit
reruns via WAL + short timeouts. The DB path is injectable so tests use a temp file.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "triage.db"

DECISIONS = ["Contacted", "Save-offer sent", "Escalated", "Dismissed", "Snoozed"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS triage_actions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at     TEXT NOT NULL,
    customer_id   TEXT NOT NULL,
    customer_name TEXT,
    risk_tier     TEXT,
    risk_score    REAL,
    decision      TEXT NOT NULL,
    note          TEXT
);
"""

_COLUMNS = ["id", "logged_at", "customer_id", "customer_name",
            "risk_tier", "risk_score", "decision", "note"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path: Path | str = DEFAULT_DB) -> None:
    """Create the DB file + table if missing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.commit()


def record_action(customer_id: str, customer_name: str, risk_tier: str,
                  risk_score: float, decision: str, note: str = "",
                  path: Path | str = DEFAULT_DB) -> int:
    """Persist one triage decision. Returns the new row id."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    init_db(path)
    with sqlite3.connect(path, timeout=10) as conn:
        cur = conn.execute(
            """INSERT INTO triage_actions
               (logged_at, customer_id, customer_name, risk_tier, risk_score, decision, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_now_iso(), customer_id, customer_name, risk_tier,
             float(risk_score), decision, note.strip()),
        )
        conn.commit()
        return int(cur.lastrowid)


def read_actions(path: Path | str = DEFAULT_DB) -> pd.DataFrame:
    """Return the full action log (most recent first)."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    with sqlite3.connect(path, timeout=10) as conn:
        return pd.read_sql_query(
            "SELECT * FROM triage_actions ORDER BY id DESC", conn)


def latest_decisions(path: Path | str = DEFAULT_DB) -> dict[str, str]:
    """Map customer_id -> most recent decision, for showing live queue status."""
    df = read_actions(path)
    if df.empty:
        return {}
    # rows are newest-first; keep the first decision seen per customer
    out: dict[str, str] = {}
    for cid, decision in zip(df["customer_id"], df["decision"]):
        out.setdefault(cid, decision)
    return out


if __name__ == "__main__":
    init_db()
    print("Initialized", DEFAULT_DB)
