from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from aiogram import Dispatcher
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


def _heartbeat_interval_minutes(settings: Settings) -> int:
    cands = [
        settings.diagnostics_interval_minutes,
        settings.metrics_summary_interval_minutes,
    ]
    positive = [x for x in cands if x > 0]
    return min(positive) if positive else 0


async def main() -> None:
    settings = load_settings()
    validate_settings_for_launch(settings)
    setup_logging(settings.log_level, soak_test=settings.soak_test)
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

    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 30,
        },
    )
    scheduler.add_job(
        run_pipeline_wrapped,
        "interval",
        minutes=settings.pipeline_interval_minutes,
        args=[ctx],
        id="newsroom_pipeline",
        replace_existing=True,
        next_run_time=datetime.now(),
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
    logger.info("Scheduler started (pipeline every %s minutes)", settings.pipeline_interval_minutes)

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
