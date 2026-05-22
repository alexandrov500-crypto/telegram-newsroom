from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from aiogram import Dispatcher
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ai.openai_client import create_openai_client
from app import lifecycle
from app.config import Settings, load_settings
from app.health import run_startup_healthchecks
from app.telegram_bot import create_newsroom_bot
from app.telegram_polling import run_polling_supervisor
from app.telegram_runtime import (
    log_runtime_startup_banner,
    register_conflict_log_handler,
    set_polling_disabled_mode,
)
from utils.structured_log import log_event
from app.startup_notify import send_startup_banner
from app.startup_validation import validate_settings_for_launch
from bot.admin_handlers import register_handlers
from db.session import init_db
from scheduler.jobs import (
    build_pipeline_context,
    run_operational_heartbeat,
    run_operational_report,
    run_pipeline_wrapped,
)
from utils.logging_config import setup_logging
from utils.startup_recovery_hints import log_startup_recovery_hints_if_any

logger = logging.getLogger(__name__)


def _log_scheduler_jobs(scheduler: AsyncIOScheduler, *, phase: str) -> None:
    for job in scheduler.get_jobs():
        logger.info(
            "job registered: %s next_run_time=%s trigger=%s (%s)",
            job.id,
            job.next_run_time,
            job.trigger,
            phase,
        )


def _scheduler_job_executed(event: object) -> None:
    job_id = getattr(event, "job_id", "?")
    logger.info("scheduler job executed: %s", job_id)
    log_event(logger, "scheduler.job.executed", job_id=str(job_id))


def _scheduler_job_error(event: object) -> None:
    job_id = getattr(event, "job_id", "?")
    exc = getattr(event, "exception", None)
    logger.error("scheduler job error: id=%s exception=%s", job_id, exc, exc_info=exc)
    log_event(logger, "scheduler.job.error", job_id=str(job_id), error=repr(exc)[:500])


def _heartbeat_interval_minutes(settings: Settings) -> int:
    cands = [
        settings.diagnostics_interval_minutes,
        settings.metrics_summary_interval_minutes,
    ]
    positive = [x for x in cands if x > 0]
    return min(positive) if positive else 0


async def main() -> None:
    from app.runtime_lifecycle import emit_lifecycle

    settings = load_settings()
    validate_settings_for_launch(settings)
    from app.startup_lock import acquire_runtime_startup_lock

    acquire_runtime_startup_lock(settings)
    setup_logging(settings.log_level, soak_test=settings.soak_test)
    emit_lifecycle("runtime.boot", dry_run=settings.dry_run, soak_test=settings.soak_test)

    from app.operational_mode import OperationalMode, load_operational_mode, set_operational_mode
    from app.runtime_lifecycle import runtime_id
    from ops.resilience.deployment_manifest import write_deployment_manifest
    from ops.resilience.leadership import get_leadership

    from app.operational_mode import sync_operational_mode_from_env

    sync_operational_mode_from_env(settings.runtime_state_dir)
    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    leadership = get_leadership(settings.runtime_state_dir)
    lock_result = leadership.acquire_all(runtime_id=runtime_id())
    if not all(lock_result.values()):
        raise RuntimeError(f"Runtime leadership acquire failed: {lock_result}")
    write_deployment_manifest(settings, operational_mode=op_mode.value)
    log_startup_recovery_hints_if_any(settings)
    health_http_server = None
    t_db0 = time.perf_counter()
    await init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    lifecycle.log_startup_structured(settings, init_db_duration_sec=time.perf_counter() - t_db0)

    try:
        from db.runtime_ops_repository import apply_loaded_runtime_ops, load_runtime_ops_state

        apply_loaded_runtime_ops(await load_runtime_ops_state())
    except Exception as exc:
        logger.warning("Runtime ops state load skipped: %s", exc)

    from utils.redis_client import init_redis_from_settings
    from worker.job_queue import init_job_queue
    from worker.reliable_transport import init_reliable_transport

    await init_redis_from_settings(settings)
    await init_job_queue(settings)
    await init_reliable_transport(settings)

    if settings.health_http_port > 0:
        from app.health_http import serve_health_http

        health_http_server = await serve_health_http(settings)

    bot = create_newsroom_bot(settings)
    await log_runtime_startup_banner(bot, settings)
    openai = create_openai_client(
        settings.openai_api_key,
        timeout=settings.openai_http_timeout_sec,
        max_retries=settings.openai_max_retries,
    )
    from app.dependency_state import AggregateStatus, get_dependency_state

    startup = await run_startup_healthchecks(settings, bot, openai)
    if startup.aggregate == AggregateStatus.DEGRADED:
        set_operational_mode(settings.runtime_state_dir, OperationalMode.DEGRADED, reason="startup_health_degraded")
        op_mode = OperationalMode.DEGRADED
        logger.warning(
            "Starting in degraded mode (ai_pipeline=%s collector=%s)",
            startup.ai_pipeline_enabled,
            startup.collector_enabled,
        )
    try:
        await send_startup_banner(bot, settings)
    except Exception as exc:
        logger.warning("Startup banner skipped: %s", exc)

    dp = Dispatcher()
    register_handlers(dp, settings)

    deps = get_dependency_state()
    ctx = build_pipeline_context(
        settings,
        bot,
        openai,
        ai_pipeline_enabled=deps.ai_pipeline_enabled,
        collector_enabled=deps.collector_enabled,
    )

    from app.operational_mode import load_operational_mode, publish_allowed, scheduler_allowed

    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    sched_ok = scheduler_allowed(op_mode)
    logger.info(
        "operational_mode=%s scheduler_allowed=%s publish_allowed=%s "
        "collector_enabled=%s ai_pipeline_enabled=%s",
        op_mode.value,
        sched_ok,
        publish_allowed(op_mode, settings),
        deps.collector_enabled,
        deps.ai_pipeline_enabled,
    )
    if not sched_ok:
        logger.warning(
            "Pipeline scheduler ticks are DISABLED until operational_mode leaves "
            "%s (check %s/operational_mode.json)",
            op_mode.value,
            settings.runtime_state_dir,
        )

    loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler(
        event_loop=loop,
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 120,
        },
    )
    scheduler.add_listener(_scheduler_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_scheduler_job_error, EVENT_JOB_ERROR)

    pipeline_job = scheduler.add_job(
        run_pipeline_wrapped,
        "interval",
        minutes=settings.pipeline_interval_minutes,
        args=[ctx],
        id="newsroom_pipeline",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    _log_scheduler_jobs(scheduler, phase="after_add_pipeline")
    logger.info(
        "job registered: newsroom_pipeline interval_min=%s next_run_time=%s",
        settings.pipeline_interval_minutes,
        pipeline_job.next_run_time,
    )

    hb = _heartbeat_interval_minutes(settings)
    if hb > 0:
        scheduler.add_job(
            run_operational_heartbeat,
            "interval",
            minutes=hb,
            args=[ctx],
            id="newsroom_operational_heartbeat",
            replace_existing=True,
        )
        logger.info("Operational heartbeat every %s minutes (diagnostics + metrics)", hb)

    if settings.operational_report_interval_hours > 0:
        scheduler.add_job(
            run_operational_report,
            "interval",
            hours=settings.operational_report_interval_hours,
            args=[ctx],
            id="newsroom_operational_report",
            replace_existing=True,
        )
        logger.info(
            "Operational summary report every %s hours",
            settings.operational_report_interval_hours,
        )

    scheduler.start()
    scheduler.wakeup()
    logger.info("Scheduler started (pipeline every %s minutes)", settings.pipeline_interval_minutes)
    _log_scheduler_jobs(scheduler, phase="after_start")
    get_dependency_state().startup_complete = True

    bootstrap_on_start = os.getenv("PIPELINE_BOOTSTRAP_ON_START", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if bootstrap_on_start and sched_ok:

        async def _bootstrap_pipeline_tick() -> None:
            """One-shot first tick on the polling event loop (same loop as AsyncIOScheduler)."""
            await asyncio.sleep(1.0)
            logger.info("pipeline execution started (bootstrap tick)")
            log_event(logger, "scheduler.bootstrap_tick", job_id="newsroom_pipeline")
            await run_pipeline_wrapped(ctx)

        asyncio.create_task(_bootstrap_pipeline_tick(), name="newsroom_pipeline_bootstrap")
    elif not sched_ok:
        logger.warning("pipeline bootstrap tick skipped: scheduler_allowed=False")
    emit_lifecycle(
        "runtime.ready",
        ai_pipeline_enabled=deps.ai_pipeline_enabled,
        collector_enabled=deps.collector_enabled,
        aggregate_status=get_dependency_state().aggregate_status().value,
    )

    shutdown_event = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (asyncio.signal.Signals.SIGTERM, asyncio.signal.Signals.SIGINT):
            try:
                loop.add_signal_handler(sig, _request_shutdown)
            except (NotImplementedError, RuntimeError):
                pass
    except Exception:
        pass

    try:
        if settings.telegram_polling_enabled:
            await run_polling_supervisor(bot, dp, settings, shutdown_event=shutdown_event)
        else:
            set_polling_disabled_mode()
            log_event(
                logger,
                "telegram.polling.disabled",
                reason="TELEGRAM_POLLING_ENABLED=false",
                recovery="scheduler_and_health_http_continue",
            )
            await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Main polling cancelled")
        shutdown_event.set()
        raise
    finally:
        shutdown_event.set()
        try:
            await dp.stop_polling()
        except Exception:
            pass
        try:
            get_leadership(settings.runtime_state_dir).release_all()
        except Exception:
            pass
        try:
            await lifecycle.graceful_shutdown(
                scheduler=scheduler,
                openai=openai,
                bot=bot,
                dispatcher=dp,
                settings=settings,
                shutdown_scheduler_timeout=25.0,
                health_http_server=health_http_server,
            )
        except Exception as exc:
            logger.warning("Graceful shutdown failed: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
