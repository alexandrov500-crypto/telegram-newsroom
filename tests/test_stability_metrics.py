"""Stability score computation."""

from __future__ import annotations

import sqlite3

from app.observability.stability_metrics import compute_system_stability_score


def test_stability_score_empty_db(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE pipeline_ticks (
          id INTEGER PRIMARY KEY,
          tick_id TEXT,
          status TEXT,
          drafts_created INTEGER,
          failures INTEGER,
          duration_ms INTEGER,
          finished_at TEXT,
          started_at TEXT,
          detail_json TEXT
        )
        """
    )
    conn.commit()
    out = compute_system_stability_score(conn)
    conn.close()
    assert 0 <= out["system_stability_score"] <= 100
    assert "tick_duration_cv" in out
