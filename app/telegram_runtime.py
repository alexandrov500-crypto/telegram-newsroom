"""Telegram runtime identity, webhook diagnostics, and conflict observability."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from aiogram import Bot

from app.config import Settings
from app.dependency_state import DependencyStatus, get_dependency_state
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

POLLING_INSTANCE_ID = str(uuid.uuid4())


class TelegramApiMode(str, Enum):
    POLLING = "polling"
    WEBHOOK = "webhook"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    polling_instance_id: str
    hostname: str
    container_id: str
    git_sha: str
    runtime_mode: str


def resolve_git_sha() -> str:
    env_sha = os.getenv("GIT_SHA", "").strip() or os.getenv("NEWSROOM_GIT_SHA", "").strip()
    if env_sha:
        return env_sha[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        return out.decode().strip()[:40]
    except Exception:
        return "unknown"


def resolve_container_id() -> str:
    for key in ("CONTAINER_ID", "HOSTNAME"):
        val = os.getenv(key, "").strip()
        if val:
            return val[:128]
    try:
        with open("/etc/hostname", encoding="utf-8") as fh:
            return fh.read().strip()[:128]
    except OSError:
        return socket.gethostname()[:128]


def build_runtime_identity(settings: Settings) -> RuntimeIdentity:
    mode = "production-lite"
    if settings.dry_run:
        mode = "dry_run"
    elif settings.soak_test:
        mode = "soak_test"
    elif settings.safe_mode:
        mode = "safe_mode"
    if not settings.telegram_polling_enabled:
        mode = f"{mode}+polling_disabled"
    return RuntimeIdentity(
        polling_instance_id=POLLING_INSTANCE_ID,
        hostname=socket.gethostname(),
        container_id=resolve_container_id(),
        git_sha=resolve_git_sha(),
        runtime_mode=mode,
    )


def identity_log_fields(identity: RuntimeIdentity) -> dict[str, Any]:
    return {
        "polling_instance_id": identity.polling_instance_id,
        "hostname": identity.hostname,
        "container_id": identity.container_id,
        "git_sha": identity.git_sha,
        "runtime_mode": identity.runtime_mode,
    }


def _identity_from_deps() -> RuntimeIdentity:
    deps = get_dependency_state()
    return RuntimeIdentity(
        polling_instance_id=deps.polling_instance_id or POLLING_INSTANCE_ID,
        hostname=socket.gethostname(),
        container_id=resolve_container_id(),
        git_sha=resolve_git_sha(),
        runtime_mode="unknown",
    )


def identity_log_fields_from_state() -> dict[str, Any]:
    ident = _identity_from_deps()
    return {
        "polling_instance_id": ident.polling_instance_id,
        "hostname": ident.hostname,
        "container_id": ident.container_id,
        "git_sha": ident.git_sha,
        "runtime_mode": ident.runtime_mode,
    }


def _webhook_info_fields(info: Any) -> dict[str, Any]:
    last_err_date = getattr(info, "last_error_date", None)
    if isinstance(last_err_date, datetime):
        last_err_iso = last_err_date.astimezone(timezone.utc).isoformat()
    elif last_err_date:
        last_err_iso = str(last_err_date)
    else:
        last_err_iso = None
    return {
        "webhook_url": getattr(info, "url", "") or "",
        "pending_update_count": int(getattr(info, "pending_update_count", 0) or 0),
        "last_error_date": last_err_iso,
        "last_error_message": (getattr(info, "last_error_message", None) or "")[:500],
        "max_connections": getattr(info, "max_connections", None),
        "has_custom_certificate": bool(getattr(info, "has_custom_certificate", False)),
    }


async def inspect_webhook(bot: Bot, *, identity: RuntimeIdentity | None = None) -> dict[str, Any]:
    info = await bot.get_webhook_info()
    fields = _webhook_info_fields(info)
    id_fields = identity_log_fields(identity) if identity else identity_log_fields_from_state()
    log_event(logger, "telegram.webhook.info", **fields, **id_fields)
    if fields["webhook_url"]:
        log_event(logger, "telegram.webhook.detected", **fields, **id_fields)
    return fields


async def ensure_webhook_cleared_with_verify(
    bot: Bot,
    *,
    identity: RuntimeIdentity | None = None,
) -> bool:
    """Delete webhook if present; verify ``url`` is empty afterward."""
    before = await inspect_webhook(bot, identity=identity)
    if not before["webhook_url"]:
        return True
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as exc:
        log_event(
            logger,
            "telegram.webhook.delete_failed",
            recovery="continue",
            error=repr(exc)[:500],
            **(identity_log_fields(identity) if identity else identity_log_fields_from_state()),
        )
        return False
    after = await inspect_webhook(bot, identity=identity)
    cleared = not after["webhook_url"]
    if cleared:
        log_event(
            logger,
            "telegram.webhook.deleted",
            pending_update_count=after["pending_update_count"],
            verified=True,
            **(identity_log_fields(identity) if identity else identity_log_fields_from_state()),
        )
        get_dependency_state().telegram_mode = TelegramApiMode.POLLING.value
    else:
        log_event(
            logger,
            "telegram.webhook.delete_failed",
            recovery="webhook_still_set",
            webhook_url=after["webhook_url"],
            verified=False,
            **(identity_log_fields(identity) if identity else identity_log_fields_from_state()),
        )
        get_dependency_state().telegram_mode = TelegramApiMode.WEBHOOK.value
    return cleared


async def log_runtime_startup_banner(bot: Bot, settings: Settings) -> None:
    identity = build_runtime_identity(settings)
    deps = get_dependency_state()
    deps.polling_instance_id = identity.polling_instance_id
    bot_id: int | None = None
    bot_username = ""
    try:
        me = await bot.get_me()
        bot_id = me.id
        bot_username = me.username or ""
        deps.bot_id = bot_id
        deps.bot_username = bot_username
    except Exception as exc:
        log_event(logger, "telegram.runtime.banner_bot_probe_failed", error=repr(exc)[:300])
    log_event(
        logger,
        "telegram.runtime.startup_banner",
        bot_id=bot_id,
        bot_username=bot_username,
        telegram_polling_enabled=settings.telegram_polling_enabled,
        **identity_log_fields(identity),
    )


def set_polling_disabled_mode() -> None:
    deps = get_dependency_state()
    deps.telegram_mode = TelegramApiMode.DISABLED.value
    deps.polling_active = False
    deps.conflict_detected = False
    deps.set_dependency(
        "telegram_api",
        status=DependencyStatus.DEGRADED,
        detail="polling disabled via TELEGRAM_POLLING_ENABLED=false",
    )


def record_polling_conflict(
    *,
    retry_count: int,
    exc: BaseException | None = None,
    log_message: str = "",
) -> None:
    deps = get_dependency_state()
    deps.conflict_detected = True
    deps.polling_conflict_count += 1
    deps.set_dependency(
        "telegram_api",
        status=DependencyStatus.DEGRADED,
        detail="getUpdates conflict: another bot instance is polling",
    )
    fields: dict[str, Any] = {
        "retry_count": retry_count,
        "conflict_count": deps.polling_conflict_count,
        "bot_id": deps.bot_id,
        "bot_username": deps.bot_username,
        **identity_log_fields_from_state(),
    }
    if exc is not None:
        fields["exception_class"] = type(exc).__name__
        fields["exception_message"] = str(exc)[:500]
    if log_message:
        fields["log_message"] = log_message[:500]
    log_event(logger, "telegram.polling.conflict", **fields)


def clear_polling_conflict_if_calm() -> None:
    deps = get_dependency_state()
    if deps.conflict_detected and deps.polling_active:
        deps.conflict_detected = False
        deps.set_dependency(
            "telegram_api",
            status=DependencyStatus.HEALTHY,
            detail="polling",
        )


class TelegramConflictLogHandler(logging.Handler):
    """Bridge aiogram internal Conflict logs into dependency state + structured events."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        if "TelegramConflictError" not in msg and "Conflict:" not in msg:
            return
        if "getUpdates" not in msg and "getupdates" not in msg.lower():
            return
        deps = get_dependency_state()
        record_polling_conflict(retry_count=deps.polling_retry_count, log_message=msg)


_CONFLICT_HANDLER: TelegramConflictLogHandler | None = None


def register_conflict_log_handler() -> None:
    global _CONFLICT_HANDLER
    if _CONFLICT_HANDLER is not None:
        return
    handler = TelegramConflictLogHandler()
    aiogram_logger = logging.getLogger("aiogram.dispatcher")
    aiogram_logger.addHandler(handler)
    _CONFLICT_HANDLER = handler


async def run_conflict_recovery_watcher(
    poll_task: asyncio.Task[None],
    *,
    shutdown: asyncio.Event,
) -> None:
    """
    If conflicts persist, cancel polling after backoff so the supervisor reconnects.
    """
    import app.telegram_polling as tp

    last_conflict_count = 0
    while not poll_task.done() and not shutdown.is_set():
        await asyncio.sleep(10.0)
        deps = get_dependency_state()
        if not deps.conflict_detected:
            if deps.polling_active:
                clear_polling_conflict_if_calm()
            continue
        if deps.polling_conflict_count == last_conflict_count:
            continue
        last_conflict_count = deps.polling_conflict_count
        delay = tp.polling_backoff_sec(deps.polling_retry_count + 1)
        log_event(
            logger,
            "telegram.polling.retry",
            reason="conflict_recovery",
            retry_count=deps.polling_retry_count,
            backoff_sec=delay,
            conflict_count=deps.polling_conflict_count,
        )
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            pass
        if deps.polling_conflict_count >= 2 and not poll_task.done():
            log_event(logger, "telegram.polling.conflict", recovery="cancel_poll_task")
            poll_task.cancel()
