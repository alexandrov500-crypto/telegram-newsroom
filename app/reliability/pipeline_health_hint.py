"""Sync read of last pipeline tick for /health (no async session in HTTP handler)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from utils.database_url import sqlite_path_from_url


def _sqlite_db_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    return str(path) if path is not None else None


def pipeline_health_hint() -> dict[str, Any]:
    """Last persisted pipeline tick summary; empty dict if unavailable."""
    db_path = _sqlite_db_path()
    if not db_path:
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        try:
            conn = sqlite3.connect(db_path, timeout=2.0)
        except Exception:
            return {}
    try:
        row = conn.execute(
            """
            SELECT tick_id, status, started_at, finished_at, posts_collected,
                   drafts_created, failures, detail_json
            FROM pipeline_ticks
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    except Exception:
        return {}
    finally:
        conn.close()
    if not row:
        return {}
    tick_id, status, started_at, finished_at, posts, drafts, failures, detail_raw = row
    detail: dict[str, Any] = {}
    try:
        detail = json.loads(detail_raw or "{}")
    except Exception:
        pass
    hint: dict[str, Any] = {
        "last_tick_id": tick_id,
        "last_tick_status": status,
        "last_started_at": started_at,
        "last_finished_at": finished_at,
        "posts_collected": int(posts or 0),
        "drafts_created": int(drafts or 0),
        "failures": int(failures or 0),
        "summarize_idle": detail.get("summarize_idle"),
        "publish_outcome": detail.get("publish_outcome"),
    }
    if status == "running" and started_at:
        try:
            started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_sec = (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
            hint["running_age_sec"] = round(age_sec, 1)
            warn = float(os.getenv("PIPELINE_TICK_LONG_WARN_SEC", "600"))
            if age_sec > warn:
                hint["long_running"] = True
        except Exception:
            pass
    return hint
