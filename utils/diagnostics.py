from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from db.repository import count_drafts, count_raw_posts, count_unprocessed_raw_posts
from db.session import get_engine, session_scope
from utils.metrics import snapshot
from utils.observability import (
    log_openai_failure_burst,
    log_sqlite_files,
    log_telethon_reconnect_burst,
    record_diagnostics_trend,
)
from utils.structured_log import log_event

_START_MONO = time.monotonic()
_LAST_OPENAI_FAILURES_SNAPSHOT: int | None = None
_LAST_TELETHON_RECONNECTS_SNAPSHOT: int | None = None
_LAST_TELEGRAM_API_FAILURES_SNAPSHOT: int | None = None
_LAST_ADMIN_NOTIFY_FAILURES_SNAPSHOT: int | None = None


def process_uptime_sec() -> float:
    return time.monotonic() - _START_MONO


def asyncio_task_count() -> int:
    try:
        loop = asyncio.get_running_loop()
        return len(asyncio.all_tasks(loop))
    except RuntimeError:
        return 0


def _sqlite_file_path(settings: Settings) -> Path | None:
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


def db_file_size_bytes(settings: Settings) -> int | None:
    p = _sqlite_file_path(settings)
    if p is None or not p.is_file():
        return None
    try:
        return int(p.stat().st_size)
    except OSError:
        return None


def wal_file_size_bytes(settings: Settings) -> int | None:
    p = _sqlite_file_path(settings)
    if p is None:
        return None
    wal = p.parent / f"{p.name}-wal"
    if not wal.is_file():
        return 0
    try:
        return int(wal.stat().st_size)
    except OSError:
        return None


def rss_bytes_best_effort() -> int | None:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return int(usage)
        return int(usage) * 1024
    except Exception:
        return None


async def log_runtime_diagnostics(logger: logging.Logger, settings: Settings) -> None:
    global _LAST_OPENAI_FAILURES_SNAPSHOT, _LAST_TELETHON_RECONNECTS_SNAPSHOT, _LAST_TELEGRAM_API_FAILURES_SNAPSHOT, _LAST_ADMIN_NOTIFY_FAILURES_SNAPSHOT
    counts: dict[str, int] = {}
    backlog = -1
    try:
        async with session_scope() as session:
            counts["raw_posts"] = await count_raw_posts(session)
            counts["drafts"] = await count_drafts(session)
            backlog = await count_unprocessed_raw_posts(session)
    except Exception as exc:
        log_event(logger, "diagnostics.db_counts_failed", error=repr(exc))
        counts["raw_posts"] = -1
        counts["drafts"] = -1
        backlog = -1

    snap = snapshot()
    failures = int(snap.get("openai_failures", 0))
    tele = int(snap.get("telethon_reconnects", 0))
    tg_api = int(snap.get("telegram_api_failures", 0))
    admin_f = int(snap.get("admin_notify_failures", 0))

    delta_oai: int | None = None
    if _LAST_OPENAI_FAILURES_SNAPSHOT is not None:
        delta_oai = failures - _LAST_OPENAI_FAILURES_SNAPSHOT
    _LAST_OPENAI_FAILURES_SNAPSHOT = failures

    delta_tel: int | None = None
    if _LAST_TELETHON_RECONNECTS_SNAPSHOT is not None:
        delta_tel = tele - _LAST_TELETHON_RECONNECTS_SNAPSHOT
    _LAST_TELETHON_RECONNECTS_SNAPSHOT = tele

    if delta_oai is not None:
        log_openai_failure_burst(logger, settings, delta_oai)
    if delta_tel is not None:
        log_telethon_reconnect_burst(logger, settings, delta_tel)

    delta_tg: int | None = None
    if _LAST_TELEGRAM_API_FAILURES_SNAPSHOT is not None:
        delta_tg = tg_api - _LAST_TELEGRAM_API_FAILURES_SNAPSHOT
    _LAST_TELEGRAM_API_FAILURES_SNAPSHOT = tg_api
    if delta_tg is not None and delta_tg >= max(3, settings.anomaly_telethon_reconnect_burst // 2):
        log_event(
            logger,
            "ops.warn.telegram_api_failures_burst",
            failures_since_last_diag=delta_tg,
        )

    delta_adm: int | None = None
    if _LAST_ADMIN_NOTIFY_FAILURES_SNAPSHOT is not None:
        delta_adm = admin_f - _LAST_ADMIN_NOTIFY_FAILURES_SNAPSHOT
    _LAST_ADMIN_NOTIFY_FAILURES_SNAPSHOT = admin_f
    if delta_adm is not None and delta_adm >= 2:
        log_event(
            logger,
            "ops.warn.admin_notify_failures_burst",
            failures_since_last_diag=delta_adm,
        )

    db_size = db_file_size_bytes(settings)
    wal_size = wal_file_size_bytes(settings)
    rss = rss_bytes_best_effort()
    tasks = asyncio_task_count()

    log_sqlite_files(logger, db_bytes=db_size, wal_bytes=wal_size)

    log_event(
        logger,
        "diagnostics.runtime",
        asyncio_tasks=tasks,
        db_file_bytes=db_size,
        wal_file_bytes=wal_size,
        raw_posts=counts.get("raw_posts", -1),
        drafts=counts.get("drafts", -1),
        backlog_unprocessed=backlog,
        uptime_sec=round(process_uptime_sec(), 1),
        openai_failures_total=failures,
        openai_failures_since_last_diag=delta_oai,
        telethon_reconnects_total=tele,
        telethon_reconnects_since_last_diag=delta_tel,
        telegram_api_failures_total=tg_api,
        telegram_api_failures_since_last_diag=delta_tg,
        admin_notify_failures_total=admin_f,
        admin_notify_failures_since_last_diag=delta_adm,
        rss_bytes=rss,
        soak_test=settings.soak_test,
    )

    record_diagnostics_trend(
        logger,
        settings,
        tasks=tasks,
        rss=rss,
        raw_posts=int(counts.get("raw_posts", -1)),
        backlog_unprocessed=backlog,
    )


async def quick_db_ping_ok() -> bool:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
