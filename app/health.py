from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from aiogram import Bot
from openai import AsyncOpenAI
from sqlalchemy import text

from app.config import Settings
from app.dependency_state import AggregateStatus, DependencyStatus, get_dependency_state
from app.telethon_bootstrap import (
    TELETHON_RECOVERY_CLI,
    telethon_missing_detail,
    telethon_session_configured,
)
from collector.telethon_client import build_telethon_client
from db.session import get_engine
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TELEGRAM_HEALTH_RETRIES = 2


@dataclass(slots=True)
class StartupHealthResult:
    aggregate: AggregateStatus
    fatal_errors: list[str]
    ai_pipeline_enabled: bool
    collector_enabled: bool
    duration_sec: float = 0.0


def _is_openai_region_blocked(exc: BaseException) -> bool:
    text_l = str(exc).lower()
    if "unsupported_country_region_territory" in text_l:
        return True
    if "country, region, or territory not supported" in text_l:
        return True
    try:
        from openai import PermissionDeniedError

        if isinstance(exc, PermissionDeniedError):
            body = getattr(exc, "body", None) or {}
            err = body.get("error") if isinstance(body, dict) else {}
            if isinstance(err, dict) and err.get("code") == "unsupported_country_region_territory":
                return True
    except ImportError:
        pass
    return False


async def _await_with_timeout(coro: Awaitable[T], timeout_sec: float) -> T:
    return await asyncio.wait_for(coro, timeout=timeout_sec)


async def _run_with_timeout_retries(
    *,
    label: str,
    timeout_sec: float,
    max_retries: int,
    run: Callable[[], Awaitable[T]],
    log_prefix: str = "healthcheck",
) -> T:
    last_exc: BaseException | None = None
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return await _await_with_timeout(run(), timeout_sec)
        except TimeoutError as exc:
            last_exc = exc
            log_event(
                logger,
                f"{log_prefix}.timeout",
                label=label,
                attempt=attempt,
                attempts=attempts,
                timeout_sec=timeout_sec,
            )
            if attempt < attempts:
                delay = 2 ** (attempt - 1)
                log_event(
                    logger,
                    f"{log_prefix}.retry",
                    label=label,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    backoff_sec=delay,
                )
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
    assert last_exc is not None
    raise last_exc


async def _check_telegram_bot(settings: Settings, bot: Bot) -> None:
    timeout_sec = settings.healthcheck_timeout_sec
    log_event(logger, "telegram.healthcheck.started", timeout_sec=timeout_sec)
    t0 = time.perf_counter()

    async def _get_me():
        return await bot.get_me()

    me = await _run_with_timeout_retries(
        label="telegram_bot_get_me",
        timeout_sec=timeout_sec,
        max_retries=_TELEGRAM_HEALTH_RETRIES,
        run=_get_me,
        log_prefix="telegram.healthcheck",
    )
    duration_sec = round(time.perf_counter() - t0, 4)
    log_event(
        logger,
        "telegram.healthcheck.success",
        bot_id=me.id,
        username=me.username or "",
        duration_sec=duration_sec,
    )
    log_event(
        logger,
        "healthcheck.telegram.bot_ok",
        bot_id=me.id,
        username=me.username or "",
        duration_sec=duration_sec,
    )


async def _check_openai(settings: Settings, openai: AsyncOpenAI) -> DependencyStatus:
    openai_timeout = settings.openai_request_timeout_sec
    try:
        await _await_with_timeout(
            openai.models.retrieve(settings.openai_model),
            openai_timeout,
        )
        log_event(
            logger,
            "healthcheck.openai_ok",
            model=settings.openai_model,
            timeout_sec=openai_timeout,
        )
        return DependencyStatus.HEALTHY
    except Exception as exc:
        if _is_openai_region_blocked(exc):
            log_event(
                logger,
                "openai.availability.degraded",
                reason="unsupported_country_region_territory",
                recovery="ai_pipeline_disabled",
                error=repr(exc)[:500],
            )
            return DependencyStatus.DEGRADED
        logger.warning("Healthcheck: OpenAI API failed (degraded): %s", exc)
        return DependencyStatus.DEGRADED


async def _check_telethon(settings: Settings) -> DependencyStatus:
    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )
    hc_timeout = settings.healthcheck_timeout_sec
    try:

        async def _telethon() -> None:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("session not authorized")

        await _run_with_timeout_retries(
            label="telethon_connect",
            timeout_sec=hc_timeout,
            max_retries=_TELEGRAM_HEALTH_RETRIES,
            run=_telethon,
            log_prefix="healthcheck.telethon",
        )
        log_event(logger, "healthcheck.telegram.telethon_ok")
        return DependencyStatus.HEALTHY
    except RuntimeError as exc:
        if "not authorized" in str(exc).lower() or "session not authorized" in str(exc).lower():
            log_event(
                logger,
                "telethon.session.unauthorized",
                recovery_cli=TELETHON_RECOVERY_CLI.splitlines()[0],
            )
            get_dependency_state().set_dependency(
                "telethon",
                status=DependencyStatus.DEGRADED,
                detail=str(exc),
                recovery_hint=TELETHON_RECOVERY_CLI,
            )
            return DependencyStatus.DEGRADED
        logger.warning("Healthcheck: Telethon failed (degraded): %s", exc)
        return DependencyStatus.DEGRADED
    except Exception as exc:
        logger.warning("Healthcheck: Telethon connect failed (degraded): %s", exc)
        return DependencyStatus.DEGRADED
    finally:
        if client.is_connected():
            await client.disconnect()


def _apply_startup_to_registry(
    result: StartupHealthResult,
    *,
    db_status: DependencyStatus,
    db_detail: str,
    telegram_status: DependencyStatus,
    telegram_detail: str,
    openai_status: DependencyStatus,
    openai_detail: str,
    telethon_status: DependencyStatus,
    telethon_detail: str,
    telethon_hint: str = "",
) -> None:
    deps = get_dependency_state()
    deps.set_dependency("database", status=db_status, detail=db_detail)
    deps.set_dependency("telegram_api", status=telegram_status, detail=telegram_detail)
    deps.set_dependency("openai", status=openai_status, detail=openai_detail)
    deps.set_dependency(
        "telethon",
        status=telethon_status,
        detail=telethon_detail,
        recovery_hint=telethon_hint,
    )
    deps.ai_pipeline_enabled = result.ai_pipeline_enabled
    deps.collector_enabled = result.collector_enabled
    deps.startup_complete = not result.fatal_errors
    agg = result.aggregate
    log_event(
        logger,
        "startup.dependencies",
        aggregate=agg.value,
        ai_pipeline_enabled=result.ai_pipeline_enabled,
        collector_enabled=result.collector_enabled,
        dependencies=deps.dependencies_dict(),
    )


async def run_startup_healthchecks(
    settings: Settings,
    bot: Bot,
    openai: AsyncOpenAI,
) -> StartupHealthResult:
    t_all0 = time.perf_counter()
    fatal_errors: list[str] = []
    hc_timeout = settings.healthcheck_timeout_sec

    db_status = DependencyStatus.HEALTHY
    db_detail = ""
    try:
        engine = get_engine()

        async def _db() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await _await_with_timeout(_db(), hc_timeout)
        log_event(logger, "healthcheck.database_ok")
    except Exception as exc:
        db_status = DependencyStatus.UNAVAILABLE
        db_detail = repr(exc)
        fatal_errors.append(f"database: {exc}")
        logger.exception("Healthcheck: database failed (fatal)")

    try:
        from utils.redis_client import redis_client_active, redis_ping_ok

        if settings.redis_enabled:
            if redis_client_active():
                pr = await _await_with_timeout(redis_ping_ok(), hc_timeout)
                if pr is True:
                    log_event(logger, "healthcheck.redis_ok")
                else:
                    log_event(logger, "healthcheck.redis_degraded", recovery="ping_failed_non_fatal")
            else:
                log_event(logger, "healthcheck.redis_skipped", recovery="enabled_but_not_connected")
    except Exception as exc:
        log_event(logger, "healthcheck.redis_check_failed", error=repr(exc), recovery="non_fatal")

    from app.runtime_metrics import inc_openai_failure_total

    openai_status = await _check_openai(settings, openai)
    if openai_status != DependencyStatus.HEALTHY:
        inc_openai_failure_total()
    openai_detail = ""
    if openai_status != DependencyStatus.HEALTHY:
        openai_detail = "AI pipeline disabled at startup"

    telegram_status = DependencyStatus.HEALTHY
    telegram_detail = ""
    try:
        await _check_telegram_bot(settings, bot)
    except Exception as exc:
        telegram_status = DependencyStatus.DEGRADED
        telegram_detail = repr(exc)
        logger.warning("Healthcheck: Telegram bot degraded: %s", exc)

    telethon_hint = ""
    if not telethon_session_configured(settings):
        telethon_status = DependencyStatus.DEGRADED
        telethon_detail = telethon_missing_detail(settings)
        telethon_hint = TELETHON_RECOVERY_CLI
        log_event(
            logger,
            "telethon.session.missing",
            detail=telethon_detail,
            recovery_cli=TELETHON_RECOVERY_CLI.splitlines()[0],
        )
    else:
        telethon_status = await _check_telethon(settings)
        telethon_detail = get_dependency_state().telethon.detail
        telethon_hint = get_dependency_state().telethon.recovery_hint

    ai_pipeline_enabled = openai_status == DependencyStatus.HEALTHY
    collector_enabled = telethon_status == DependencyStatus.HEALTHY

    if fatal_errors:
        aggregate = AggregateStatus.UNHEALTHY
    elif any(
        s != DependencyStatus.HEALTHY
        for s in (openai_status, telethon_status, telegram_status)
    ):
        aggregate = AggregateStatus.DEGRADED
    else:
        aggregate = AggregateStatus.HEALTHY

    duration_sec = round(time.perf_counter() - t_all0, 4)
    result = StartupHealthResult(
        aggregate=aggregate,
        fatal_errors=fatal_errors,
        ai_pipeline_enabled=ai_pipeline_enabled,
        collector_enabled=collector_enabled,
        duration_sec=duration_sec,
    )

    _apply_startup_to_registry(
        result,
        db_status=db_status,
        db_detail=db_detail,
        telegram_status=telegram_status,
        telegram_detail=telegram_detail,
        openai_status=openai_status,
        openai_detail=openai_detail,
        telethon_status=telethon_status,
        telethon_detail=telethon_detail,
        telethon_hint=telethon_hint,
    )

    if fatal_errors:
        msg = "; ".join(fatal_errors)
        log_event(logger, "healthcheck.failed", duration_sec=duration_sec, error_count=len(fatal_errors))
        raise RuntimeError(f"Startup healthchecks failed: {msg}")

    if aggregate == AggregateStatus.DEGRADED:
        log_event(
            logger,
            "healthcheck.degraded_startup",
            duration_sec=duration_sec,
            ai_pipeline_enabled=ai_pipeline_enabled,
            collector_enabled=collector_enabled,
            recovery="continue_runtime",
        )
    else:
        log_event(logger, "healthcheck.all_ok", duration_sec=duration_sec)

    return result
