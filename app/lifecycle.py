from __future__ import annotations

import asyncio
import logging
import platform
import sys
import threading
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_shutdown_lock = threading.Lock()
_shutdown_done = threading.Event()


def reset_shutdown_state_for_tests() -> None:
    """Clear idempotent shutdown gate (pytest only)."""
    _shutdown_done.clear()


def _database_diagnostics(settings: Any) -> dict[str, Any]:
    url = str(getattr(settings, "database_url", "") or "")
    out: dict[str, Any] = {"database_backend": "unknown"}
    if "sqlite" in url.lower():
        out["database_backend"] = "sqlite"
        try:
            from sqlalchemy.engine.url import make_url

            u = make_url(url)
            db = u.database
            if db and db != ":memory:":
                out["sqlite_file"] = str(Path(db).name)
            else:
                out["sqlite_file"] = ":memory:"
        except Exception:
            out["sqlite_file"] = "unparsed"
    elif "postgresql" in url.lower():
        out["database_backend"] = "postgresql"
    return out


def log_startup_structured(settings: Any, *, init_db_duration_sec: float | None = None) -> None:
    """Structured startup banner — no tokens or API keys."""
    db = _database_diagnostics(settings)
    try:
        from app.versioning import public_metadata

        ver = public_metadata()
    except Exception:
        ver = {}
    log_event(
        logger,
        "startup.banner",
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        dry_run=bool(getattr(settings, "dry_run", False)),
        safe_mode=bool(getattr(settings, "safe_mode", False)),
        soak_test=bool(getattr(settings, "soak_test", False)),
        **ver,
        log_level=str(getattr(settings, "log_level", "")),
        pipeline_interval_minutes=int(getattr(settings, "pipeline_interval_minutes", 0)),
        collect_messages_per_channel=int(getattr(settings, "collect_messages_per_channel", 0)),
        raw_fetch_cap=int(getattr(settings, "raw_fetch_cap", 0)),
        max_cluster_posts=int(getattr(settings, "max_cluster_posts", 0)),
        openai_model=str(getattr(settings, "openai_model", "")),
        source_channel_count=len(getattr(settings, "source_channels", ()) or ()),
        admin_user_id=int(getattr(settings, "admin_user_id", 0)),
        target_channel_id=int(getattr(settings, "target_channel_id", 0)),
        init_db_duration_sec=round(init_db_duration_sec, 4) if init_db_duration_sec is not None else None,
        **db,
    )


async def shutdown_collector_runtime() -> None:
    from collector.service import shutdown_collector_hooks

    await shutdown_collector_hooks()
    log_event(logger, "lifecycle.collector_shutdown_complete")


async def shutdown_pipeline_jobs() -> None:
    from scheduler.runtime_context import set_pipeline_context

    set_pipeline_context(None)
    log_event(logger, "lifecycle.pipeline_context_cleared")


async def graceful_shutdown(
    *,
    scheduler: Any = None,
    openai: Any = None,
    bot: Any = None,
    dispatcher: Any = None,
    settings: Any = None,
    shutdown_scheduler_timeout: float = 25.0,
    health_http_server: Any = None,
) -> bool:
    """
    Idempotent process shutdown: scheduler, DB, OpenAI, bot session, pipeline context.
    Returns False if shutdown already ran in this process.
    """
    with _shutdown_lock:
        if _shutdown_done.is_set():
            log_event(logger, "lifecycle.shutdown_idempotent_skip")
            return False
        _shutdown_done.set()

    from app.runtime_lifecycle import emit_lifecycle

    emit_lifecycle("runtime.shutdown.started")
    log_event(logger, "runtime.shutdown.started")
    try:
        if dispatcher is not None:
            try:
                await dispatcher.stop_polling()
                log_event(logger, "runtime.shutdown.polling_stopped")
            except Exception as exc:
                log_event(logger, "runtime.shutdown.polling_stop_failed", error=repr(exc))

        if scheduler is not None:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(scheduler.shutdown, True),
                    timeout=shutdown_scheduler_timeout,
                )
            except asyncio.TimeoutError:
                log_event(logger, "lifecycle.scheduler_shutdown_timeout", recovery="force_no_wait")
                try:
                    await asyncio.to_thread(scheduler.shutdown, False)
                except Exception as exc2:
                    log_event(logger, "lifecycle.scheduler_shutdown_force_failed", error=repr(exc2))
            except Exception as exc:
                log_event(logger, "lifecycle.scheduler_shutdown_failed", error=repr(exc))

        from db.session import close_db

        from app.health_http import stop_health_server
        from utils.redis_client import close_redis
        from worker.job_queue import close_job_queue
        from worker.reliable_transport import close_reliable_transport

        await close_reliable_transport()
        await close_job_queue()
        await close_redis()
        await stop_health_server(health_http_server)

        await close_db()

        if openai is not None:
            try:
                await openai.close()
            except Exception as exc:
                log_event(logger, "lifecycle.openai_close_failed", error=repr(exc))

        if bot is not None:
            try:
                await bot.session.close()
            except Exception as exc:
                log_event(logger, "lifecycle.bot_session_close_failed", error=repr(exc))

        await shutdown_pipeline_jobs()
        await shutdown_collector_runtime()

        if settings is not None:
            try:
                from db.runtime_ops_repository import persist_runtime_ops_state

                await persist_runtime_ops_state()
            except Exception as exc:
                log_event(logger, "runtime.shutdown.ops_persist_failed", error=repr(exc))

        if settings is not None:
            from utils.runtime_state_store import try_save_runtime_snapshot

            try_save_runtime_snapshot(settings, "shutdown")

        try:
            loop = asyncio.get_running_loop()
            current = asyncio.current_task()
            pending = [t for t in asyncio.all_tasks(loop) if t is not current and not t.done()]
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.wait(pending, timeout=4.0)
        except Exception as exc:
            log_event(logger, "lifecycle.task_sweep_failed", error=repr(exc))

        emit_lifecycle("runtime.shutdown.completed")
        log_event(logger, "runtime.shutdown.completed")
        log_event(logger, "lifecycle.shutdown_complete")
        return True
    except Exception as exc:
        log_event(logger, "lifecycle.shutdown_inner_failed", error=repr(exc))
        return True
