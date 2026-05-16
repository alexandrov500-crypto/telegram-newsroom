from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_LAST_ANALYZE_MONO = time.monotonic()
_LAST_VACUUM_MONO = time.monotonic()


def _sqlite_path(settings: Settings) -> Path | None:
    try:
        from sqlalchemy.engine.url import make_url

        u = make_url(settings.database_url)
        if u.get_backend_name() != "sqlite":
            return None
        db = u.database
        if not db or db == ":memory:":
            return None
        return Path(db).expanduser().resolve()
    except Exception:
        return None


async def maybe_run_sqlite_maintenance(settings: Settings) -> None:
    """Run ANALYZE / VACUUM on wall-clock intervals (idle tail of pipeline)."""
    global _LAST_ANALYZE_MONO, _LAST_VACUUM_MONO
    path = _sqlite_path(settings)
    if path is None or not path.is_file():
        return

    now = time.monotonic()
    hours = 3600.0

    if settings.sqlite_analyze_interval_hours > 0:
        due = (now - _LAST_ANALYZE_MONO) >= settings.sqlite_analyze_interval_hours * hours
        if due:
            try:
                from db.session import get_engine

                engine = get_engine()
                async with engine.begin() as conn:
                    await conn.execute(text("ANALYZE"))
                _LAST_ANALYZE_MONO = now
                log_event(logger, "sqlite.maintenance_analyze_ok", path=str(path))
            except Exception as exc:
                log_event(logger, "sqlite.maintenance_analyze_failed", error=repr(exc))

    if settings.sqlite_vacuum_interval_hours > 0:
        due_v = (now - _LAST_VACUUM_MONO) >= settings.sqlite_vacuum_interval_hours * hours
        if due_v:
            try:
                before = path.stat().st_size if path.is_file() else None

                def _vacuum() -> None:
                    con = sqlite3.connect(str(path), timeout=60.0)
                    try:
                        con.execute("VACUUM")
                    finally:
                        con.close()

                await asyncio.to_thread(_vacuum)
                _LAST_VACUUM_MONO = now
                after = path.stat().st_size if path.is_file() else None
                log_event(
                    logger,
                    "sqlite.maintenance_vacuum_ok",
                    path=str(path),
                    db_bytes_before=before,
                    db_bytes_after=after,
                )
            except Exception as exc:
                log_event(logger, "sqlite.maintenance_vacuum_failed", error=repr(exc))
