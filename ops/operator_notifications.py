"""Structured operational notifications (Telegram + logs, rate-limited)."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)
_lock = threading.RLock()
_sent_keys: dict[str, float] = {}


def _pending_path(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "ops"
    p.mkdir(parents=True, exist_ok=True)
    return p / "pending_notifications.jsonl"


def enqueue_operator_notification(
    runtime_dir: str,
    *,
    kind: str,
    severity: str,
    message: str,
    fields: dict[str, Any] | None = None,
    group_key: str = "",
) -> None:
    from ops.alert_discipline import AlertSeverity, normalize_severity, should_emit_alert

    sev = normalize_severity(severity)
    if not should_emit_alert(kind, severity=sev, group_key=group_key or kind):
        log_event(
            logger,
            "operator.notification.suppressed",
            kind=kind,
            severity=sev.value,
            reason="cooldown",
        )
        return
    row = {
        "ts_unix": time.time(),
        "kind": kind[:60],
        "severity": sev.value[:20],
        "message": message[:400],
        "fields": fields or {},
        "group_key": (group_key or kind)[:80],
    }
    path = _pending_path(runtime_dir)
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    log_event(logger, "operator.notification.enqueued", kind=kind, severity=sev.value, detail=message[:200])


def _dedupe_key(kind: str, message: str) -> str:
    return f"{kind}:{message[:80]}"


def _should_send(kind: str, message: str, window_sec: float) -> bool:
    key = _dedupe_key(kind, message)
    now = time.monotonic()
    with _lock:
        last = _sent_keys.get(key)
        if last is not None and (now - last) < window_sec:
            return False
        _sent_keys[key] = now
    return True


async def flush_pending_notifications(bot: Any, settings: Any) -> int:
    """Send queued notifications to admin chat (called from heartbeat)."""
    if not getattr(settings, "admin_user_id", 0):
        return 0
    path = _pending_path(settings.runtime_state_dir)
    if not path.is_file():
        return 0
    window = float(getattr(settings, "notification_rate_limit_minutes", 15) or 15) * 60.0
    sent = 0
    remaining: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    from aiogram.enums import ParseMode

    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = str(row.get("kind") or "ops")
        msg = str(row.get("message") or "")
        sev = str(row.get("severity") or "info")
        if not _should_send(kind, msg, window):
            continue
        icon = {
            "critical": "🔴",
            "warning": "🟠",
            "info": "ℹ️",
            "high": "🔴",
            "medium": "🟠",
        }.get(sev, "ℹ️")
        text = f"{icon} <b>{kind}</b>\n{msg[:500]}"
        try:
            await bot.send_message(
                settings.admin_user_id,
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            sent += 1
            log_event(logger, "operator.notification.sent", kind=kind, severity=sev)
        except Exception as exc:
            remaining.append(line)
            log_event(logger, "operator.notification.failed", kind=kind, detail=repr(exc)[:200])
    try:
        path.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
    except OSError:
        pass
    return sent


async def notify_runtime_degraded(bot: Any, settings: Any, *, reason: str) -> None:
    enqueue_operator_notification(
        settings.runtime_state_dir,
        kind="runtime_degraded",
        severity="medium",
        message=f"Runtime degraded: {reason[:200]}",
    )
    await flush_pending_notifications(bot, settings)


async def notify_publish_halted(bot: Any, settings: Any, *, mode: str) -> None:
    enqueue_operator_notification(
        settings.runtime_state_dir,
        kind="publish_halted",
        severity="high",
        message=f"Publishing blocked (mode={mode})",
    )
    await flush_pending_notifications(bot, settings)


def notify_drift_warning(runtime_dir: str, warnings: list[str]) -> None:
    enqueue_operator_notification(
        runtime_dir,
        kind="editorial_drift",
        severity="medium",
        message="Drift: " + ", ".join(warnings[:6]),
        fields={"warnings": warnings},
    )
