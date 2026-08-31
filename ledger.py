"""
The ledger — your record of who's connecting, what they call, and what you earn.

Every guarded operation is recorded here (SQLite, stdlib only, survives
restarts). payments.check_payment() writes to it, so both http_server.py and
mcp_server.py log automatically. The dashboard reads from it.

Event kinds:
  paid       — a verified payment; `amount_atomic` is revenue
  challenge  — a 402 was issued (an agent knocked but hasn't paid yet)
  rejected   — a payment was submitted but failed verification (reason logged)
  free       — a free tool was called (e.g. get_pricing)

The DB file lives next to the code as data/ledger.db (LEDGER_DB overrides).
"""
from __future__ import annotations
import os
import sqlite3
import threading
import time
from pathlib import Path

_DB_PATH = os.getenv(
    "LEDGER_DB", str(Path(__file__).resolve().parent / "data" / "ledger.db")
)
_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                tool TEXT NOT NULL,
                payer TEXT,
                amount_atomic INTEGER NOT NULL DEFAULT 0,
                network TEXT,
                detail TEXT
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")
        conn.commit()
        _local.conn = conn
    return conn


def record(kind: str, tool: str, payer: str | None = None,
           amount_atomic: int = 0, network: str | None = None,
           detail: str | None = None) -> None:
    conn = _conn()
    conn.execute(
        "INSERT INTO events (ts, kind, tool, payer, amount_atomic, network, detail)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (time.time(), kind, tool, payer, amount_atomic, network, detail),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Queries for the dashboard
# ---------------------------------------------------------------------------
def summary() -> dict:
    """Everything the dashboard needs, in one call."""
    conn = _conn()
    day_ago = time.time() - 86400

    def one(sql: str, *args):
        return conn.execute(sql, args).fetchone()

    totals = one(
        "SELECT COALESCE(SUM(amount_atomic),0) AS revenue, COUNT(*) AS n"
        " FROM events WHERE kind='paid'"
    )
    mock = one(
        "SELECT COALESCE(SUM(amount_atomic),0) AS revenue, COUNT(*) AS n"
        " FROM events WHERE kind='paid' AND detail='mock'"
    )
    today = one(
        "SELECT COALESCE(SUM(amount_atomic),0) AS revenue, COUNT(*) AS n"
        " FROM events WHERE kind='paid' AND ts>=?"
        " AND COALESCE(detail,'') <> 'mock'", day_ago,
    )
    payers = one(
        "SELECT COUNT(DISTINCT payer) AS n FROM events"
        " WHERE kind='paid' AND payer IS NOT NULL"
    )
    rejected = one("SELECT COUNT(*) AS n FROM events WHERE kind='rejected'")
    challenges = one("SELECT COUNT(*) AS n FROM events WHERE kind='challenge'")

    # Aggregations below count ON-CHAIN revenue only; mock-mode payments stay
    # visible in the recent-activity feed but never inflate the numbers.
    not_mock = " AND COALESCE(detail,'') <> 'mock'"
    by_tool = [
        dict(r) for r in conn.execute(
            "SELECT tool, COUNT(*) AS calls, COALESCE(SUM(amount_atomic),0) AS revenue"
            " FROM events WHERE kind='paid'" + not_mock +
            " GROUP BY tool ORDER BY revenue DESC"
        )
    ]
    top_payers = [
        dict(r) for r in conn.execute(
            "SELECT payer, COUNT(*) AS calls, COALESCE(SUM(amount_atomic),0) AS revenue"
            " FROM events WHERE kind='paid' AND payer IS NOT NULL" + not_mock +
            " GROUP BY payer ORDER BY revenue DESC LIMIT 10"
        )
    ]
    recent = [
        dict(r) for r in conn.execute(
            "SELECT ts, kind, tool, payer, amount_atomic, detail"
            " FROM events WHERE kind <> 'interest' ORDER BY id DESC LIMIT 50"
        )
    ]
    # Demand signal from the landing page: who asked about the service.
    interest = [
        dict(r) for r in conn.execute(
            "SELECT ts, payer AS contact, detail AS note"
            " FROM events WHERE kind='interest' ORDER BY id DESC LIMIT 25"
        )
    ]
    # last 14 days of daily revenue (paid events only), oldest first
    daily = [
        dict(r) for r in conn.execute(
            "SELECT date(ts,'unixepoch','localtime') AS day,"
            " COALESCE(SUM(amount_atomic),0) AS revenue, COUNT(*) AS calls"
            " FROM events WHERE kind='paid' AND ts>=?" + not_mock +
            " GROUP BY day ORDER BY day", (time.time() - 14 * 86400,),
        )
    ]
    return {
        "revenue_atomic": totals["revenue"],
        "revenue_mock_atomic": mock["revenue"],
        "paid_calls": totals["n"],
        "paid_calls_mock": mock["n"],
        "revenue_today_atomic": today["revenue"],
        "paid_calls_today": today["n"],
        "unique_payers": payers["n"],
        "rejected": rejected["n"],
        "challenges": challenges["n"],
        "by_tool": by_tool,
        "top_payers": top_payers,
        "recent": recent,
        "interest": interest,
        "daily": daily,
    }
