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
    validate_settings_for_launch(settings)  # includes operational invariant assert
    from app.startup_validation import warn_duplicate_runtime_startup_risk

    warn_duplicate_runtime_startup_risk(settings)

    # 1) Single-runtime guarantee (exit 0 if duplicate container/process)
    from app.ops.runtime import enforce_singleton_or_exit, register_active_runtime

    enforce_singleton_or_exit(settings)

    setup_logging(settings.log_level, soak_test=settings.soak_test)
    try:
        from publisher.telegram_forensic import log_runtime_code_identity

        log_runtime_code_identity(bot_token=settings.bot_token)
    except Exception as exc:
        log_event(logger, "runtime.code_identity_failed", error=repr(exc)[:200])
    emit_lifecycle("runtime.boot", dry_run=settings.dry_run, soak_test=settings.soak_test)

    from app.operational_mode import OperationalMode, load_operational_mode, set_operational_mode
    from app.runtime_lifecycle import runtime_id

    # 2) Register active runtime (atomic active_runtime.json)
    register_active_runtime(settings.runtime_state_dir, runtime_id=runtime_id())

    from app.ops.runtime.execution_lease import clear_stale_lease, try_acquire_lease
    from app.ops.runtime.node_role import (
        RuntimeNodeRole,
        apply_execution_profile_to_deps,
        log_execution_profile,
        resolve_execution_profile,
    )

    execution_profile = resolve_execution_profile(settings)
    log_execution_profile(execution_profile)
    apply_execution_profile_to_deps(execution_profile)
    from app.dependency_state import get_dependency_state

    get_dependency_state().execution_profile = execution_profile.to_dict()

    clear_stale_lease(settings.runtime_state_dir)
    if execution_profile.node_role == RuntimeNodeRole.WORKER:
        acquired, lease = try_acquire_lease(
            settings.runtime_state_dir,
            owner_id=execution_profile.owner_id,
            runtime_id=runtime_id(),
            node_role=execution_profile.node_role.value,
        )
        if not acquired and lease is not None:
            raise RuntimeError(
                f"Execution lease held by {lease.owner_id!r} — stop other newsroom process or "
                f"clear stale lease in {settings.runtime_state_dir}"
            )

    # 3) OPS control plane state
    from app.ops.control_plane import init_ops_state_store

    init_ops_state_store(settings.runtime_state_dir)

    # 4) Idempotent ingestion store (sqlite, survives restart)
    from app.ingestion.idempotency import init_idempotency_store

    init_idempotency_store(settings.runtime_state_dir)

    from app.ops.ledger.event_ledger import init_event_ledger

    init_event_ledger(settings.runtime_state_dir)

    import os as _os_replay

    if _os_replay.getenv("REPLAY_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}:
        logger.warning(
            "REPLAY_MODE enabled — collector will replay from event ledger only (no Telegram reads)"
        )
    from ops.resilience.deployment_manifest import write_deployment_manifest
    from ops.resilience.leadership import get_leadership

    from app.operational_mode import sync_operational_mode_from_env

    sync_operational_mode_from_env(settings.runtime_state_dir)
    from app.ops.runtime_control import sync_runtime_control_from_env

    sync_runtime_control_from_env(settings.runtime_state_dir)
    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    leadership = get_leadership(settings.runtime_state_dir)
    lock_result = leadership.acquire_all(runtime_id=runtime_id())
    if not all(lock_result.values()):
        raise RuntimeError(f"Runtime leadership acquire failed: {lock_result}")
    write_deployment_manifest(settings, operational_mode=op_mode.value)
    from app.reliability.checkpoint import bootstrap_runtime_state
    from app.reliability.shutdown import install_signal_handlers

    bootstrap_runtime_state(settings)
    install_signal_handlers(asyncio.get_running_loop())
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
        from app.reliability.stale_tick_recovery import reconcile_stale_pipeline_ticks

        stale_rec = await reconcile_stale_pipeline_ticks(settings, source="startup")
        if stale_rec.get("count"):
            log_event(
                logger,
                "pipeline.startup_stale_reconciled",
                finalized=stale_rec.get("finalized"),
                count=stale_rec.get("count"),
            )
    except Exception as exc:
        logger.warning("Stale tick reconciliation skipped: %s", exc)

    if os.getenv("BACKUP_ON_STARTUP", "true").strip().lower() in ("1", "true", "yes"):
        try:
            from app.reliability.sqlite_backup import backup_sqlite_database

            backup_sqlite_database(runtime_dir=settings.runtime_state_dir)
        except Exception as exc:
            logger.warning("Startup SQLite backup skipped: %s", exc)
    if os.getenv("SQLITE_CHECKPOINT_ON_STARTUP", "true").strip().lower() in ("1", "true", "yes"):
        try:
            from app.reliability.sqlite_safety import sqlite_safety_pass

            sqlite_safety_pass(settings)
        except Exception as exc:
            logger.warning("Startup SQLite safety skipped: %s", exc)

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

    deps = get_dependency_state()
    if not execution_profile.collector_enabled:
        deps.collector_enabled = False

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

    @dp.errors()
    async def on_dispatcher_error(event: object) -> bool:
        from aiogram.types import ErrorEvent

        if not isinstance(event, ErrorEvent):
            return False
        exc = event.exception
        log_event(
            logger,
            "bot.dispatcher.error",
            error=repr(exc)[:500],
            update_id=getattr(event.update, "update_id", None),
        )
        logger.exception("dispatcher error")
        return True

    register_handlers(dp, settings)

    deps = get_dependency_state()
    try:
        from app.state.pipeline_decision_engine import apply_pipeline_decision
        from app.state.pipeline_execution_wrapper import pipeline_evaluation_only

        with pipeline_evaluation_only():
            apply_pipeline_decision(source="main_startup")
    except Exception:
        pass

    ctx = build_pipeline_context(
        settings,
        bot,
        openai,
        ai_pipeline_enabled=deps.ai_pipeline_enabled,
        collector_enabled=deps.collector_enabled,
    )

    from app.operational_mode import load_operational_mode, publish_allowed, scheduler_allowed

    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    sched_ok = scheduler_allowed(op_mode) and execution_profile.scheduler_enabled
    logger.info(
        "operational_mode=%s scheduler_allowed=%s publish_allowed=%s "
        "node_role=%s collector_enabled=%s ai_pipeline_enabled=%s",
        op_mode.value,
        sched_ok,
        publish_allowed(op_mode, settings) and execution_profile.publish_enabled,
        execution_profile.node_role.value,
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

    if sched_ok:
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

        if os.getenv("TELEGRAM_ANALYTICS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            from app.analytics.scheduler_jobs import run_analytics_tick

            analytics_min = max(5, int(os.getenv("TELEGRAM_ANALYTICS_INTERVAL_MIN", "15")))
            scheduler.add_job(
                run_analytics_tick,
                "interval",
                minutes=analytics_min,
                args=[ctx],
                id="telegram_analytics",
                replace_existing=True,
            )
            logger.info("Telegram analytics poll every %s minutes", analytics_min)

        if os.getenv("BREAKING_LANE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            from app.lanes.breaking_pipeline import run_breaking_tick

            breaking_min = max(1, int(os.getenv("BREAKING_LANE_INTERVAL_MIN", "3")))
            scheduler.add_job(
                run_breaking_tick,
                "interval",
                minutes=breaking_min,
                args=[ctx],
                id="breaking_lane",
                replace_existing=True,
            )
            logger.info("Breaking lane tick every %s minutes", breaking_min)

        if os.getenv("GROWTH_DIGEST_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            from app.digest.scheduler_jobs import run_digest_tick

            scheduler.add_job(
                run_digest_tick,
                "interval",
                minutes=max(30, int(os.getenv("GROWTH_DIGEST_CHECK_INTERVAL_MIN", "60"))),
                args=[ctx],
                id="growth_digest",
                replace_existing=True,
            )
            logger.info("Growth digest check every %s minutes", os.getenv("GROWTH_DIGEST_CHECK_INTERVAL_MIN", "60"))

        # 5–6) Lane workers (fast/standard) then start scheduler pipeline
        if execution_profile.lane_workers_enabled:
            try:
                from app.ops.runtime.pipeline_gate import require_processing_or_skip
                from app.worker.lane_runtime import start_lane_workers

                if require_processing_or_skip(component="lane_workers"):
                    start_lane_workers(ctx)
                else:
                    logger.warning("lane workers not started: pipeline_gate blocked")
            except Exception as exc:
                logger.warning("Fast lane workers not started: %s", exc)

        scheduler.start()
        scheduler.wakeup()
        logger.info("Scheduler started (pipeline every %s minutes)", settings.pipeline_interval_minutes)
        _log_scheduler_jobs(scheduler, phase="after_start")
    else:
        logger.warning(
            "Scheduler NOT started (operational_mode=%s node_role=%s)",
            op_mode.value,
            execution_profile.node_role.value,
        )
    get_dependency_state().startup_complete = True

    try:
        from app.runtime.task_watchdog import start_task_watchdog

        start_task_watchdog()
    except Exception as exc:
        log_event(logger, "task_watchdog.start_failed", error=repr(exc)[:200])

    async def _execution_lease_heartbeat() -> None:
        from app.ops.runtime.execution_lease import heartbeat_lease

        while True:
            await asyncio.sleep(30.0)
            heartbeat_lease(
                settings.runtime_state_dir,
                owner_id=execution_profile.owner_id,
                runtime_id=runtime_id(),
                node_role=execution_profile.node_role.value,
            )

    if execution_profile.node_role == RuntimeNodeRole.WORKER:
        from app.runtime.task_orchestrator import create_traced_task

        create_traced_task(
            "execution_lease_heartbeat",
            _execution_lease_heartbeat(),
            trace_id="lease-heartbeat",
            owner="app.main",
            metadata={"task_type": "heartbeat"},
            name="execution_lease_heartbeat",
        )

    bootstrap_on_start = os.getenv("PIPELINE_BOOTSTRAP_ON_START", "false").strip().lower() in {
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

        from app.runtime.task_orchestrator import create_traced_task

        create_traced_task(
            "newsroom_pipeline_bootstrap",
            _bootstrap_pipeline_tick(),
            trace_id="pipeline-bootstrap",
            owner="app.main",
            metadata={"task_type": "pipeline", "phase": "collect"},
            name="newsroom_pipeline_bootstrap",
        )
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
        poll_enabled = settings.telegram_polling_enabled and execution_profile.polling_enabled
        if poll_enabled:
            await run_polling_supervisor(bot, dp, settings, shutdown_event=shutdown_event)
        else:
            set_polling_disabled_mode()
            reason = (
                "RUNTIME_NODE_ROLE=control"
                if not execution_profile.polling_enabled
                else "TELEGRAM_POLLING_ENABLED=false"
            )
            log_event(
                logger,
                "telegram.polling.disabled",
                reason=reason,
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
            from app.ops.runtime.execution_lease import release_lease

            release_lease(
                settings.runtime_state_dir,
                owner_id=execution_profile.owner_id,
            )
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
