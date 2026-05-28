"""SQLite backup, integrity check, size metrics."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

from utils.database_url import sqlite_path_from_url
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _backup_dir(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "backups" / "sqlite"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _max_backups() -> int:
    raw = os.getenv("SQLITE_BACKUP_KEEP", "7").strip()
    try:
        return max(2, min(int(raw), 30))
    except ValueError:
        return 7


def backup_sqlite_database(settings: Any, *, tag: str = "manual") -> Path | None:
    db_path = sqlite_path_from_url(settings.database_url)
    if db_path is None or not db_path.is_file():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    dest = _backup_dir(settings.runtime_state_dir) / f"newsroom_{tag}_{ts}.db"
    shutil.copy2(db_path, dest)
    _rotate_backups(settings.runtime_state_dir)
    log_event(logger, "sqlite.backup_created", path=str(dest), tag=tag)
    return dest


def _rotate_backups(runtime_dir: str) -> None:
    files = sorted(_backup_dir(runtime_dir).glob("newsroom_*.db"), key=lambda p: p.stat().st_mtime)
    keep = _max_backups()
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def run_sqlite_integrity_check(settings: Any) -> dict[str, Any]:
    db_path = sqlite_path_from_url(settings.database_url)
    if db_path is None or not db_path.is_file():
        return {"ok": True, "skipped": "not_sqlite"}
    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
            ok = row is not None and str(row[0]).lower() == "ok"
            journal = conn.execute("PRAGMA journal_mode;").fetchone()
            return {
                "ok": ok,
                "integrity": str(row[0]) if row else "",
                "journal_mode": str(journal[0]) if journal else "",
                "bytes": db_path.stat().st_size,
            }
        finally:
            conn.close()
    except Exception as exc:
        return {"ok": False, "error": repr(exc)[:300]}


def sqlite_metrics(settings: Any) -> dict[str, Any]:
    db_path = sqlite_path_from_url(settings.database_url)
    if db_path is None:
        return {}
    try:
        return {"path": str(db_path), "bytes": db_path.stat().st_size if db_path.is_file() else 0}
    except OSError:
        return {}
