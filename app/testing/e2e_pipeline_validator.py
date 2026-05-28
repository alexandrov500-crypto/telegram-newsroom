"""Deterministic end-to-end pipeline validator (dry-run, no Telegram side effects)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _runtime_dir() -> Path:
    return Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")).expanduser().resolve()


def _db_path() -> Path | None:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    p = sqlite_path_from_url(raw)
    return Path(p) if p else None


def _stage_transition_correctness(conn: sqlite3.Connection) -> dict[str, Any]:
    # Stage correctness should not require "no tick in progress" —
    # on a live VPS there may be an active tick while we validate the last
    # finished ticks and the execution graph integrity.
    total = conn.execute(
        "SELECT COUNT(*) FROM pipeline_ticks WHERE started_at >= datetime('now', '-24 hours')"
    ).fetchone()
    finished = conn.execute(
        "SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NOT NULL AND started_at >= datetime('now', '-24 hours')"
    ).fetchone()
    running = conn.execute("SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NULL").fetchone()
    return {
        "ticks_24h": int((total or [0])[0] or 0),
        "finished_24h": int((finished or [0])[0] or 0),
        "running_now": int((running or [0])[0] or 0),
    }


def _publish_finalize_consistency(conn: sqlite3.Connection) -> dict[str, Any]:
    dup = conn.execute(
        "SELECT COUNT(*) FROM (SELECT telegram_post_id, COUNT(*) c FROM published_posts GROUP BY telegram_post_id HAVING c>1)"
    ).fetchone()
    no_final = conn.execute(
        """
        SELECT COUNT(*) FROM published_posts pp
        JOIN drafts d ON d.id = pp.draft_id
        WHERE COALESCE(d.status, '') NOT IN ('published', 'approved', 'committed_draft')
        """
    ).fetchone()
    return {
        "duplicate_publish_paths": int((dup or [0])[0] or 0),
        "publish_without_finalize_proxy": int((no_final or [0])[0] or 0),
    }


def _graph_consistency(runtime_dir: Path, db_path: Path | None) -> dict[str, Any]:
    from app.observability.execution_graph_report import build_execution_graph_report

    eg = build_execution_graph_report(
        db_path=db_path if db_path and db_path.is_file() else None,
        runtime_dir=runtime_dir,
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
        window_ticks=200,
    )
    return {
        "execution_graph_ready": bool(eg.get("execution_graph_ready")),
        "consistency_rate": eg.get("consistency_rate"),
        "critical_tick_count": eg.get("critical_tick_count"),
        "execution_graph_verdict": eg.get("verdict"),
        "db_missing_terminal": eg.get("db_missing_terminal"),
        "db_invalid_status": eg.get("db_invalid_status"),
    }


def run_e2e_validation() -> dict[str, Any]:
    runtime_dir = _runtime_dir()
    db_path = _db_path()
    if not db_path or not db_path.is_file():
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "error": "database_missing",
        }
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        transitions = _stage_transition_correctness(conn)
        publish = _publish_finalize_consistency(conn)
    finally:
        conn.close()
    graph = _graph_consistency(runtime_dir, db_path)
    ticks = int(transitions.get("ticks_24h") or 0)
    finished = int(transitions.get("finished_24h") or 0)
    tick_success_rate = round((finished / max(1, ticks)) * 100.0, 2)
    # Allow running ticks; only require at least one finished tick in window.
    stage_ok = finished >= 1
    publish_ok = (
        int(publish.get("duplicate_publish_paths") or 0) == 0
        and int(publish.get("publish_without_finalize_proxy") or 0) == 0
    )
    graph_ok = str(graph.get("execution_graph_verdict") or "") == "PASS"
    ok = bool(stage_ok and publish_ok and graph_ok)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run_mode": True,
        "ok": ok,
        "tick_success_rate": tick_success_rate,
        "graph_consistency_rate": graph.get("consistency_rate")
        if graph.get("consistency_rate") is not None
        else "UNKNOWN",
        "stage_transition_correctness": stage_ok,
        "failure_classification": {
            "graph": "PASS" if graph_ok else "graph_inconsistency",
            "publish": "PASS" if publish_ok else "publish_path_violation",
            "stages": "PASS" if stage_ok else "no_finished_ticks_or_incomplete_window",
        },
        "details": {
            "transitions": transitions,
            "publish": publish,
            "graph": graph,
        },
    }


def write_e2e_validation_report(report: dict[str, Any]) -> Path:
    out = _runtime_dir() / "e2e_validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


async def run_e2e_validation_heartbeat(settings: Any) -> dict[str, Any]:
    report = run_e2e_validation()
    write_e2e_validation_report(report)
    return report
