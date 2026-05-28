"""Execution graph report builder."""

from __future__ import annotations

import json
import sqlite3

from app.observability.execution_graph_report import build_execution_graph_report


def test_report_ready_on_clean_trace(tmp_path):
    traces = tmp_path / "execution_graph_traces.jsonl"
    row = {
        "tick_id": "tick-1",
        "summarize_calls": 1,
        "finalize_calls": 1,
        "publish_gate_allowed": 0,
        "publish_success": 0,
        "terminal_state": "committed_idle",
        "anomalies": [],
    }
    traces.write_text("\n".join(json.dumps(row) for _ in range(3)) + "\n", encoding="utf-8")

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE pipeline_ticks (
          id INTEGER PRIMARY KEY, tick_id TEXT, status TEXT,
          finished_at TEXT, started_at TEXT, duration_ms INTEGER, detail_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO pipeline_ticks (tick_id, status, finished_at, started_at, detail_json)
        VALUES ('tick-1', 'ok', datetime('now'), datetime('now'),
                '{"terminal_state":"committed_idle"}')
        """
    )
    conn.commit()
    conn.close()

    report = build_execution_graph_report(
        db_path=db,
        runtime_dir=tmp_path,
        log_path=tmp_path / "missing.log",
        window_ticks=10,
    )
    assert report["consistency_rate"] == 1.0
    assert report["execution_graph_ready"] is True
