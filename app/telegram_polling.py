"""Self-healing long-running Telegram bot polling for unstable networks."""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import ClientError
from aiogram import Bot, Dispatcher
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramConflictError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)

from app.config import Settings
from app.dependency_state import DependencyStatus, get_dependency_state
from app.telegram_runtime import (
    TelegramApiMode,
    build_runtime_identity,
    clear_polling_conflict_if_calm,
    ensure_webhook_cleared_with_verify,
    record_polling_conflict,
    register_conflict_log_handler,
    run_conflict_recovery_watcher,
)
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

POLLING_BACKOFF_SEC: tuple[float, ...] = (5.0, 10.0, 20.0, 30.0)
_PROBE_MAX_ATTEMPTS_PER_CYCLE = 4

_AUTH_FATAL_TYPES: tuple[type[BaseException], ...] = (TelegramUnauthorizedError,)


def polling_backoff_sec(retry_count: int) -> float:
    """Exponential backoff capped at 30s (5 → 10 → 20 → 30)."""
    if retry_count <= 0:
        return POLLING_BACKOFF_SEC[0]
    idx = min(retry_count - 1, len(POLLING_BACKOFF_SEC) - 1)
    return POLLING_BACKOFF_SEC[idx]


def classify_telegram_failure(exc: BaseException) -> DependencyStatus:
    """Only auth/config failures are unavailable; network/conflict is degraded."""
    if isinstance(exc, _AUTH_FATAL_TYPES):
        return DependencyStatus.UNAVAILABLE
    if isinstance(exc, TelegramConflictError):
        return DependencyStatus.DEGRADED
    if isinstance(exc, TelegramBadRequest):
        msg = str(exc).lower()
        if "token" in msg or "unauthorized" in msg:
            return DependencyStatus.UNAVAILABLE
    return DependencyStatus.DEGRADED


def is_retriable_telegram_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, _AUTH_FATAL_TYPES):
        return True
    if isinstance(exc, (TelegramConflictError, TelegramNetworkError, asyncio.TimeoutError, TimeoutError, ClientError)):
        return True
    if isinstance(exc, TelegramBadRequest):
        return classify_telegram_failure(exc) == DependencyStatus.DEGRADED
    return True


def _exc_fields(exc: BaseException | None) -> dict[str, str]:
    if exc is None:
        return {"exception_class": "", "exception_message": ""}
    return {
        "exception_class": type(exc).__name__,
        "exception_message": str(exc)[:500],
    }


def set_telegram_api_runtime(
    *,
    status: DependencyStatus,
    detail: str = "",
    mode: TelegramApiMode | None = None,
    polling_active: bool = False,
    retry_count: int = 0,
    conflict_detected: bool | None = None,
) -> None:
    deps = get_dependency_state()
    deps.set_dependency("telegram_api", status=status, detail=detail)
    deps.polling_active = polling_active
    deps.polling_retry_count = retry_count
    if mode is not None:
        deps.telegram_mode = mode.value
    if conflict_detected is not None:
        deps.conflict_detected = conflict_detected


async def run_connectivity_probe(
    bot: Bot,
    settings: Settings,
    *,
    retry_count_start: int = 0,
) -> DependencyStatus:
    """Lightweight ``get_me()`` probe with backoff; updates ``telegram_api`` dependency."""
    timeout_sec = settings.healthcheck_timeout_sec
    attempt = 0
    probe_retry = retry_count_start

    while attempt < _PROBE_MAX_ATTEMPTS_PER_CYCLE:
        attempt += 1
        t0 = time.perf_counter()
        try:
            me = await asyncio.wait_for(bot.get_me(), timeout=timeout_sec)
            duration_sec = round(time.perf_counter() - t0, 4)
            deps = get_dependency_state()
            deps.bot_id = me.id
            deps.bot_username = me.username or ""
            set_telegram_api_runtime(
                status=DependencyStatus.HEALTHY,
                detail=f"connected bot_id={me.id}",
                mode=TelegramApiMode.POLLING,
                polling_active=False,
                retry_count=0,
                conflict_detected=False,
            )
            if probe_retry > 0:
                log_event(
                    logger,
                    "telegram.polling.recovered",
                    phase="connectivity_probe",
                    retry_count=probe_retry,
                    backoff_sec=0,
                    duration_sec=duration_sec,
                    bot_id=me.id,
                    username=me.username or "",
                )
            return DependencyStatus.HEALTHY
        except Exception as exc:
            duration_sec = round(time.perf_counter() - t0, 4)
            status = classify_telegram_failure(exc)
            is_timeout = isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or (
                isinstance(exc, TelegramNetworkError) and "timeout" in str(exc).lower()
            )
            event = "telegram.polling.network_timeout" if is_timeout else "telegram.polling.retry"
            log_event(
                logger,
                event,
                phase="connectivity_probe",
                retry_count=probe_retry + 1,
                backoff_sec=polling_backoff_sec(probe_retry + 1),
                duration_sec=duration_sec,
                probe_attempt=attempt,
                dependency_status=status.value,
                **_exc_fields(exc),
            )
            set_telegram_api_runtime(
                status=status,
                detail=repr(exc)[:300],
                polling_active=False,
                retry_count=probe_retry + 1,
            )
            if status == DependencyStatus.UNAVAILABLE:
                return status
            probe_retry += 1
            delay = polling_backoff_sec(probe_retry)
            await asyncio.sleep(delay)

    return get_dependency_state().telegram_api.status


async def _run_one_polling_session(
    bot: Bot,
    dp: Dispatcher,
    *,
    allowed_updates: list[str] | None,
) -> None:
    await dp.start_polling(
        bot,
        handle_signals=False,
        allowed_updates=allowed_updates,
    )


async def run_polling_supervisor(
    bot: Bot,
    dp: Dispatcher,
    settings: Settings,
    *,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """
    Infinite supervisor: webhook diagnostics → probe → poll → backoff on failure.
    Never raises retriable network/conflict errors to the caller.
    """
    register_conflict_log_handler()
    shutdown = shutdown_event or asyncio.Event()
    identity = build_runtime_identity(settings)
    deps = get_dependency_state()
    deps.polling_instance_id = identity.polling_instance_id
    allowed = dp.resolve_used_update_types()
    retry_count = 0
    was_ever_connected = False

    while not shutdown.is_set():
        cycle_retry = retry_count
        backoff = polling_backoff_sec(cycle_retry + 1) if cycle_retry > 0 else 0.0
        log_event(
            logger,
            "telegram.polling.start",
            retry_count=cycle_retry,
            backoff_sec=backoff,
            polling_instance_id=identity.polling_instance_id,
            hostname=identity.hostname,
            container_id=identity.container_id,
        )

        await ensure_webhook_cleared_with_verify(bot, identity=identity)
        probe_status = await run_connectivity_probe(bot, settings, retry_count_start=cycle_retry)

        if probe_status == DependencyStatus.UNAVAILABLE:
            retry_count += 1
            delay = polling_backoff_sec(retry_count)
            log_event(
                logger,
                "telegram.polling.retry",
                retry_count=retry_count,
                backoff_sec=delay,
                reason="auth_unavailable",
                dependency_status="unavailable",
            )
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                continue

        t_poll0 = time.perf_counter()
        try:
            set_telegram_api_runtime(
                status=DependencyStatus.HEALTHY,
                detail="polling",
                mode=TelegramApiMode.POLLING,
                polling_active=True,
                retry_count=0,
                conflict_detected=False,
            )
            log_event(
                logger,
                "telegram.polling.connected",
                retry_count=cycle_retry,
                duration_sec=round(time.perf_counter() - t_poll0, 4),
                bot_id=deps.bot_id,
                bot_username=deps.bot_username,
                polling_instance_id=identity.polling_instance_id,
            )
            if was_ever_connected and cycle_retry > 0:
                log_event(
                    logger,
                    "telegram.polling.recovered",
                    retry_count=cycle_retry,
                    backoff_sec=0,
                    duration_sec=round(time.perf_counter() - t_poll0, 4),
                )
            was_ever_connected = True
            retry_count = 0

            poll_task = asyncio.create_task(
                _run_one_polling_session(bot, dp, allowed_updates=allowed),
                name="telegram_polling",
            )
            conflict_watch = asyncio.create_task(
                run_conflict_recovery_watcher(poll_task, shutdown=shutdown),
                name="telegram_conflict_watch",
            )
            stop_wait = asyncio.create_task(shutdown.wait(), name="polling_shutdown_wait")
            done, pending = await asyncio.wait(
                {poll_task, stop_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            conflict_watch.cancel()
            for t in pending:
                t.cancel()
            if poll_task in done:
                if poll_task.cancelled():
                    retry_count = max(retry_count, get_dependency_state().polling_retry_count) + 1
                    delay = polling_backoff_sec(retry_count)
                    log_event(
                        logger,
                        "telegram.polling.retry",
                        reason="poll_task_cancelled",
                        retry_count=retry_count,
                        backoff_sec=delay,
                    )
                    set_telegram_api_runtime(
                        status=DependencyStatus.DEGRADED,
                        detail="polling session cancelled for recovery",
                        polling_active=False,
                        retry_count=retry_count,
                        conflict_detected=get_dependency_state().conflict_detected,
                    )
                    try:
                        await dp.stop_polling()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(shutdown.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        continue
                exc = poll_task.exception()
                if exc is not None:
                    raise exc
            else:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
                await dp.stop_polling()
                log_event(logger, "telegram.polling.stopped", reason="shutdown")
                break

        except asyncio.CancelledError:
            log_event(logger, "telegram.polling.cancelled")
            raise
        except Exception as exc:
            if isinstance(exc, TelegramConflictError):
                record_polling_conflict(retry_count=retry_count + 1, exc=exc)
            if not is_retriable_telegram_error(exc):
                logger.exception("telegram.polling.fatal_unexpected")
                raise

            duration_sec = round(time.perf_counter() - t_poll0, 4)
            status = classify_telegram_failure(exc)
            retry_count += 1
            delay = polling_backoff_sec(retry_count)
            is_timeout = isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or (
                isinstance(exc, TelegramNetworkError) and "timeout" in str(exc).lower()
            )
            if isinstance(exc, TelegramConflictError):
                event = "telegram.polling.conflict"
            elif is_timeout:
                event = "telegram.polling.network_timeout"
            else:
                event = "telegram.polling.retry"
            log_event(
                logger,
                event,
                retry_count=retry_count,
                backoff_sec=delay,
                duration_sec=duration_sec,
                dependency_status=status.value,
                bot_id=deps.bot_id,
                bot_username=deps.bot_username,
                polling_instance_id=identity.polling_instance_id,
                hostname=identity.hostname,
                container_id=identity.container_id,
                **_exc_fields(exc),
            )
            set_telegram_api_runtime(
                status=status,
                detail=repr(exc)[:300],
                mode=TelegramApiMode.POLLING,
                polling_active=False,
                retry_count=retry_count,
                conflict_detected=isinstance(exc, TelegramConflictError) or deps.conflict_detected,
            )
            try:
                await dp.stop_polling()
            except Exception:
                pass

            try:
                await asyncio.wait_for(shutdown.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                continue
