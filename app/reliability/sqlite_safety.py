"""SQLite integrity + WAL checkpoint (read-only ops, safe on running DB)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from utils.database_url import sqlite_path_from_url
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def sqlite_db_path(settings: Any | None = None) -> Path | None:
    import os

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    if settings is not None:
        raw = str(getattr(settings, "database_url", raw))
    p = sqlite_path_from_url(raw)
    return Path(p) if p else None


def run_wal_checkpoint(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path), timeout=30.0)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
        log_event(logger, "sqlite.wal_checkpoint_ok", path=str(path))
        return True
    except Exception as exc:
        log_event(logger, "sqlite.wal_checkpoint_failed", error=repr(exc)[:200])
        return False


def check_sqlite_integrity(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path), timeout=30.0)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            ok = row is not None and str(row[0]).lower() == "ok"
        finally:
            conn.close()
        log_event(logger, "sqlite.integrity_check", ok=ok, path=str(path))
        return ok
    except Exception as exc:
        log_event(logger, "sqlite.integrity_check_failed", error=repr(exc)[:200])
        return False


def sqlite_safety_pass(settings: Any | None = None) -> dict[str, Any]:
    path = sqlite_db_path(settings)
    if not path or not path.is_file():
        return {"ok": False, "reason": "no_db"}
    wal_ok = run_wal_checkpoint(path)
    int_ok = check_sqlite_integrity(path)
    return {"ok": wal_ok and int_ok, "path": str(path), "wal_checkpoint": wal_ok, "integrity": int_ok}
