"""Final release checklist tool."""

from __future__ import annotations

import json
import sqlite3

from tools.final_release_checklist import run_checklist


def test_final_release_checklist_structure(tmp_path, monkeypatch):
    db = tmp_path / "r.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE published_posts (id INTEGER PRIMARY KEY, draft_id INT, telegram_post_id INT, published_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE pipeline_ticks (id INTEGER PRIMARY KEY, tick_id TEXT, status TEXT, started_at TEXT, finished_at TEXT, detail_json TEXT)"
    )
    conn.execute(
        "INSERT INTO published_posts (draft_id, telegram_post_id, published_at) VALUES (1,1,datetime('now'))"
    )
    conn.execute(
        "INSERT INTO pipeline_ticks (tick_id, status, started_at, finished_at, detail_json) VALUES ('t','ok',datetime('now'),datetime('now'),'{}')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("RUNTIME_STATE_DIR", str(tmp_path))
    out_path = tmp_path / "FINAL_RELEASE_REPORT.json"
    report = run_checklist(write_report=out_path)
    assert report["FINAL_RELEASE_VERDICT"] in {"BLOCKED", "CONDITIONAL", "APPROVED"}
    assert out_path.is_file()
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["FINAL_RELEASE_VERDICT"] == report["FINAL_RELEASE_VERDICT"]
