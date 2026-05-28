"""Burn-in eval unit tests (in-memory SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.observability.burnin_eval import (
    build_snapshot,
    evaluate_readiness,
    fetch_finished_ticks,
    tail_consecutive_finished_streak,
)


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE pipeline_ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tick_id TEXT NOT NULL UNIQUE,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_ms INTEGER,
            drafts_created INTEGER DEFAULT 0,
            posts_collected INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            node_name TEXT DEFAULT '',
            correlation_id TEXT DEFAULT '',
            detail_json TEXT DEFAULT '{}'
        )
        """
    )


def _insert(
    conn: sqlite3.Connection,
    *,
    status: str,
    finished: bool,
    terminal_state: str = "",
    draft_id: int | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    detail = {"terminal_state": terminal_state}
    if draft_id is not None:
        detail["draft_id"] = draft_id
    import json

    conn.execute(
        """
        INSERT INTO pipeline_ticks
        (tick_id, started_at, finished_at, status, detail_json, drafts_created)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            f"tick-{conn.execute('SELECT COUNT(*)+1 FROM pipeline_ticks').fetchone()[0]}",
            now,
            now if finished else None,
            status,
            json.dumps(detail),
            1 if draft_id else 0,
        ),
    )


@pytest.fixture
def mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    _init_db(conn)
    yield conn
    conn.close()


def test_tail_streak_stops_at_running(mem_db: sqlite3.Connection) -> None:
    _insert(mem_db, status="reject", finished=True, terminal_state="committed_reject")
    _insert(mem_db, status="running", finished=False)
    _insert(mem_db, status="ok", finished=True, terminal_state="committed_idle")
    ids = mem_db.execute(
        "SELECT id, finished_at FROM pipeline_ticks ORDER BY id DESC"
    ).fetchall()
    assert tail_consecutive_finished_streak([(int(i), f) for i, f in ids]) == 1


def test_readiness_pass_three_consecutive(mem_db: sqlite3.Connection) -> None:
    for _ in range(3):
        _insert(mem_db, status="reject", finished=True, terminal_state="committed_reject")
    finished = fetch_finished_ticks(mem_db, limit=10)
    log_scan = {"available": True, "aborted_draft": 0, "pipeline_fatal_break": 0}
    verdict, reasons = evaluate_readiness(
        tail_streak=finished[:3],
        streak_count=3,
        log_scan=log_scan,
        min_ticks=3,
    )
    assert verdict == "PASS"
    assert not reasons


def test_readiness_fail_missing_terminal(mem_db: sqlite3.Connection) -> None:
    for _ in range(3):
        _insert(mem_db, status="ok", finished=True, terminal_state="")
    finished = fetch_finished_ticks(mem_db, limit=10)
    verdict, reasons = evaluate_readiness(
        tail_streak=finished[:3],
        streak_count=3,
        log_scan={"available": True, "aborted_draft": 0, "pipeline_fatal_break": 0},
    )
    assert verdict == "FAIL"
    assert any("missing_terminal_state" in r for r in reasons)


def test_readiness_fail_aborted_draft_in_log(mem_db: sqlite3.Connection) -> None:
    for _ in range(3):
        _insert(mem_db, status="ok", finished=True, terminal_state="committed_idle")
    finished = fetch_finished_ticks(mem_db, limit=10)
    verdict, _ = evaluate_readiness(
        tail_streak=finished[:3],
        streak_count=3,
        log_scan={"available": True, "aborted_draft": 2, "pipeline_fatal_break": 0},
    )
    assert verdict == "FAIL"


def test_snapshot_separates_active(mem_db: sqlite3.Connection, tmp_path: Path) -> None:
    _insert(mem_db, status="reject", finished=True, terminal_state="committed_reject")
    _insert(mem_db, status="running", finished=False)
    log = tmp_path / "test.log"
    log.write_text("no violations here\n", encoding="utf-8")
    snap = build_snapshot(mem_db, finished_limit=5, log_path=log)
    assert snap["verdict"] in ("PASS", "CONDITIONAL", "FAIL")
    assert len(snap["active_ticks"]) == 1
    assert len(snap["finished_ticks"]) == 1
    assert snap["finished_metrics"]["count"] == 1


def test_log_scan_counts_signals(tmp_path: Path) -> None:
    from app.observability.burnin_eval import scan_log_contract

    log = tmp_path / "run.log"
    log.write_text(
        "aborted_draft\nPIPELINE_FATAL_BREAK\n"
        'pipeline.terminal_state\n"summarize_exit"\n'
        "openai.summarize_failed 429 RateLimit\nrule_fallback_starvation\n",
        encoding="utf-8",
    )
    s = scan_log_contract(log)
    assert s["aborted_draft"] == 1
    assert s["pipeline_fatal_break"] == 1
    assert s["pipeline_terminal_state"] >= 1


def test_since_id_filters_finished(mem_db: sqlite3.Connection) -> None:
    _insert(mem_db, status="ok", finished=True, terminal_state="committed_idle")
    first_id = mem_db.execute("SELECT MIN(id) FROM pipeline_ticks").fetchone()[0]
    _insert(mem_db, status="reject", finished=True, terminal_state="committed_reject")
    rows = fetch_finished_ticks(mem_db, limit=10, since_id=int(first_id) + 1)
    assert len(rows) == 1
    assert rows[0].terminal_state == "committed_reject"
