"""Process-scoped Telegram ops notifications (startup vs polling recovery)."""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import Settings
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

PROCESS_RUNTIME_UUID = str(uuid.uuid4())

_startup_notification_sent = False
_last_notification_mono: dict[str, float] = {}
_persisted_last_startup_at_unix: float | None = None


def reset_notification_state_for_tests() -> None:
    """Clear in-process notification gates (pytest only)."""
    global _startup_notification_sent, _last_notification_mono, _persisted_last_startup_at_unix
    _startup_notification_sent = False
    _last_notification_mono.clear()
    _persisted_last_startup_at_unix = None
    try:
        from app.ops.runtime.startup_notify_guard import reset_startup_notification_lock_for_tests

        reset_startup_notification_lock_for_tests()
    except Exception:
        pass


def apply_persisted_notification_state(*, last_startup_notification_at_unix: float | None) -> None:
    global _persisted_last_startup_at_unix
    _persisted_last_startup_at_unix = last_startup_notification_at_unix


def _persisted_notification_fields() -> dict[str, Any]:
    out: dict[str, Any] = {
        "process_runtime_uuid": PROCESS_RUNTIME_UUID,
        "startup_notification_sent": _startup_notification_sent,
    }
    if _persisted_last_startup_at_unix is not None:
        out["last_startup_notification_at_unix"] = _persisted_last_startup_at_unix
    for kind, mono in _last_notification_mono.items():
        out[f"last_{kind}_notification_mono"] = mono
    return out


def notification_state_for_persist() -> dict[str, Any]:
    return _persisted_notification_fields()


def _rate_limit_ok(kind: str, settings: Settings) -> bool:
    window_sec = settings.notification_rate_limit_minutes * 60.0
    if window_sec <= 0:
        return True
    last = _last_notification_mono.get(kind)
    if last is None:
        return True
    return (time.monotonic() - last) >= window_sec


def _persisted_startup_within_rate_limit(settings: Settings) -> bool:
    if _persisted_last_startup_at_unix is None:
        return False
    window_sec = settings.notification_rate_limit_minutes * 60.0
    if window_sec <= 0:
        return False
    return (time.time() - _persisted_last_startup_at_unix) < window_sec


def _mark_sent(kind: str) -> None:
    global _startup_notification_sent, _persisted_last_startup_at_unix
    _last_notification_mono[kind] = time.monotonic()
    if kind == "startup":
        _startup_notification_sent = True
        _persisted_last_startup_at_unix = time.time()
    _schedule_persist()


def _schedule_persist() -> None:
    try:
        from db.runtime_ops_repository import persist_runtime_ops_state_fire_and_forget

        persist_runtime_ops_state_fire_and_forget()
    except Exception:
        pass


async def maybe_send_process_startup_notification(
    bot: Bot,
    settings: Settings,
    *,
    trigger: str = "process_boot",
) -> bool:
    """
    Full process startup banner — at most once per process lifetime (+ rate limit across restarts).
    Never call from polling supervisor reconnect paths.
    """
    global _startup_notification_sent

    if not settings.send_startup_notification:
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="disabled",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
        )
        return False

    if _startup_notification_sent:
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="already_sent_this_process",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
        )
        return False

    if _persisted_startup_within_rate_limit(settings):
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="rate_limited_persisted_startup",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
            rate_limit_minutes=settings.notification_rate_limit_minutes,
        )
        return False

    if not _rate_limit_ok("startup", settings):
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="rate_limited",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
            rate_limit_minutes=settings.notification_rate_limit_minutes,
        )
        return False

    window_sec = max(0.0, float(settings.notification_rate_limit_minutes) * 60.0)
    try:
        from db.runtime_ops_repository import try_claim_startup_notification_in_db
        from db.session import session_scope

        async with session_scope() as session:
            claimed = await try_claim_startup_notification_in_db(
                session,
                window_sec=window_sec if window_sec > 0 else 86400.0,
                process_uuid=PROCESS_RUNTIME_UUID,
            )
        if not claimed:
            log_event(
                logger,
                "runtime.startup.notification.skipped",
                reason="db_startup_claim_recent",
                trigger=trigger,
                process_runtime_uuid=PROCESS_RUNTIME_UUID,
                rate_limit_minutes=settings.notification_rate_limit_minutes,
            )
            return False
    except Exception as exc:
        log_event(
            logger,
            "runtime.startup.notification.db_claim_skipped",
            error=repr(exc)[:200],
            trigger=trigger,
        )
        return False

    from app.ops.runtime.active_runtime import load_active_runtime
    from app.ops.runtime.lock_paths import resolve_process_lock_dir
    from app.ops.runtime.singleton_guard import get_singleton_guard
    from app.ops.runtime.startup_notify_guard import try_acquire_startup_notification_lock

    lock_dir = resolve_process_lock_dir(settings)

    from app.ops.runtime.startup_notify_cooldown import try_claim_startup_notify_cooldown

    if not try_claim_startup_notify_cooldown(lock_dir, window_sec=window_sec if window_sec > 0 else 86400.0):
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="startup_notify_cooldown_file",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
            lock_dir=lock_dir,
        )
        return False
    active = load_active_runtime(settings.runtime_state_dir)
    if active is not None and int(active.get("pid") or 0) not in (0, os.getpid()):
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="not_active_runtime_owner",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
            active_pid=active.get("pid"),
            our_pid=os.getpid(),
        )
        return False

    if not try_acquire_startup_notification_lock(lock_dir):
        log_event(
            logger,
            "runtime.startup.notification.skipped",
            reason="startup_notify_lock_held",
            trigger=trigger,
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
        )
        return False

    if os.getenv("RUNTIME_SINGLETON_DISABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        sg = get_singleton_guard()
        if sg is not None and not sg.is_owner():
            log_event(
                logger,
                "runtime.startup.notification.skipped",
                reason="not_singleton_lock_owner",
                trigger=trigger,
                process_runtime_uuid=PROCESS_RUNTIME_UUID,
            )
            return False

    import socket

    host = socket.gethostname()[:64]
    rdir = str(getattr(settings, "runtime_state_dir", "") or os.getenv("RUNTIME_STATE_DIR", "?"))[:120]
    lines = [
        "<b>Newsroom started</b>",
        f"DRY_RUN=<code>{settings.dry_run}</code>",
        f"SOAK_TEST=<code>{settings.soak_test}</code>",
        f"source_channels={len(settings.source_channels)}",
        f"pipeline_interval_min={settings.pipeline_interval_minutes}",
        f"runtime_id=<code>{PROCESS_RUNTIME_UUID[:8]}</code>",
        f"pid=<code>{os.getpid()}</code>",
        f"host=<code>{host}</code>",
        f"runtime_dir=<code>{rdir}</code>",
    ]
    try:
        await bot.send_message(
            settings.admin_user_id,
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log_event(
            logger,
            "runtime.startup.notification.failed",
            trigger=trigger,
            error=repr(exc)[:500],
            process_runtime_uuid=PROCESS_RUNTIME_UUID,
        )
        return False

    _mark_sent("startup")
    log_event(
        logger,
        "runtime.startup.notification.sent",
        trigger=trigger,
        admin_user_id=settings.admin_user_id,
        process_runtime_uuid=PROCESS_RUNTIME_UUID,
    )
    return True


async def maybe_send_polling_recovery_notification(
    bot: Bot,
    settings: Settings,
    *,
    cause: str,
    retry_count: int = 0,
) -> bool:
    """Optional compact ops message after polling recovery (disabled by default)."""
    if not settings.send_recovery_notification:
        return False

    if not _rate_limit_ok("recovery", settings):
        log_event(
            logger,
            "runtime.recovery.notification.skipped",
            reason="rate_limited",
            cause=cause,
            rate_limit_minutes=settings.notification_rate_limit_minutes,
        )
        return False

    text = (
        "<b>Telegram polling recovered</b>\n"
        f"after <code>{cause}</code> degradation"
        + (f" (retry_count={retry_count})" if retry_count else "")
    )
    try:
        await bot.send_message(
            settings.admin_user_id,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log_event(
            logger,
            "runtime.recovery.notification.failed",
            cause=cause,
            error=repr(exc)[:500],
        )
        return False

    _mark_sent("recovery")
    log_event(
        logger,
        "runtime.recovery.notification.sent",
        cause=cause,
        retry_count=retry_count,
        process_runtime_uuid=PROCESS_RUNTIME_UUID,
    )
    return True
