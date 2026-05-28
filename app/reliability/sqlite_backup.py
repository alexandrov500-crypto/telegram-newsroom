"""SQLite backup with rotation (production-safe, no schema changes)."""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from utils.database_url import sqlite_path_from_url
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def backup_sqlite_database(
    *,
    runtime_dir: str | None = None,
    keep: int = 7,
) -> Path | None:
    """Copy SQLite DB to runtime_dir/backups/; prune old copies. Never raises."""
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    src = sqlite_path_from_url(raw)
    if not src or not Path(src).is_file():
        log_event(logger, "backup.skipped", reason="no_sqlite_path")
        return None
    base = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    dest_dir = base / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"newsroom_{stamp}.db"
    try:
        shutil.copy2(src, dest)
        log_event(logger, "backup.sqlite_completed", path=str(dest), bytes=dest.stat().st_size)
    except Exception as exc:
        log_event(logger, "backup.sqlite_failed", error=repr(exc)[:200])
        return None
    _rotate(dest_dir, keep=max(1, int(keep)))
    return dest


def _rotate(dest_dir: Path, *, keep: int) -> None:
    files = sorted(dest_dir.glob("newsroom_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
            log_event(logger, "backup.sqlite_pruned", path=str(old))
        except OSError:
            pass
