#!/usr/bin/env python3
"""Backfill incident timeline from existing publish traces (one-time migration)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_forensics.repository import ForensicsRepository
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    db = default_db_path()
    init_database(db)
    repo = ForensicsRepository(db)
    import sqlite3

    n = 0
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT pending_news_id, trace_json, created_at FROM live_publish_trace ORDER BY created_at",
        ).fetchall()
    for pid, raw, created_at in rows:
        try:
            trace = json.loads(raw)
        except json.JSONDecodeError:
            continue
        repo.append_timeline(
            event_type="publish_succeeded" if trace.get("published") else "publish_held",
            severity="info",
            details=trace,
            correlation_id=trace.get("correlation_id"),
            publish_id=pid,
            timestamp=trace.get("timestamp") or created_at,
        )
        n += 1
    print(f"Backfilled {n} timeline events from live_publish_trace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
