"""Telegram production validation — connectivity, permissions, transport health, alerts."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from utils.metrics import export_snapshot, inc
from utils.structured_log import log_event

import logging

if TYPE_CHECKING:
    from aiogram import Bot

    from app.config import Settings

logger = logging.getLogger(__name__)

_STATE_NAME = "telegram_production_state.json"


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / _STATE_NAME


def _load_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _save_state(runtime_dir: str, state: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _default_state() -> dict[str, Any]:
    return {
        "flood_wait_total": 0,
        "reconnect_total": 0,
        "api_failure_total": 0,
        "consecutive_api_failures": 0,
        "last_flood_wait_at": None,
        "last_reconnect_at": None,
        "last_api_failure_at": None,
        "last_success_at": None,
        "last_connectivity_check_at": None,
        "last_connectivity_ok": None,
        "recent_events": [],
    }


def _append_event(state: dict[str, Any], event: dict[str, Any], *, limit: int = 40) -> None:
    events = list(state.get("recent_events") or [])
    events.append(event)
    state["recent_events"] = events[-limit:]


def record_flood_wait(*, wait_sec: float = 0.0, source: str = "unknown") -> None:
    """Track FloodWait / TelegramRetryAfter (collector or publisher)."""
    inc("telethon_flood_waits")
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    state = _load_state(rd)
    state["flood_wait_total"] = int(state.get("flood_wait_total") or 0) + 1
    state["last_flood_wait_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append_event(
        state,
        {"kind": "flood_wait", "wait_sec": round(float(wait_sec), 2), "source": source[:40]},
    )
    _save_state(rd, state)
    log_event(logger, "telegram_production.flood_wait", wait_sec=wait_sec, source=source)


def record_reconnect(*, source: str = "telethon") -> None:
    """Track transport reconnect (Telethon session or polling restart)."""
    inc("telethon_reconnects")
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    state = _load_state(rd)
    state["reconnect_total"] = int(state.get("reconnect_total") or 0) + 1
    state["last_reconnect_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append_event(state, {"kind": "reconnect", "source": source[:40]})
    _save_state(rd, state)
    log_event(logger, "telegram_production.reconnect", source=source)


def record_telegram_api_failure(*, draft_id: int | None = None, error: str = "") -> None:
    """Track publisher Bot API failure (increments streak for alerting)."""
    inc("telegram_api_failures")
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    state = _load_state(rd)
    state["api_failure_total"] = int(state.get("api_failure_total") or 0) + 1
    state["consecutive_api_failures"] = int(state.get("consecutive_api_failures") or 0) + 1
    state["last_api_failure_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _append_event(
        state,
        {
            "kind": "api_failure",
            "draft_id": draft_id,
            "error": (error or "")[:200],
        },
    )
    _save_state(rd, state)
    log_event(
        logger,
        "telegram_production.api_failure",
        draft_id=draft_id,
        streak=state["consecutive_api_failures"],
    )


def record_telegram_success(*, draft_id: int | None = None) -> None:
    """Reset API failure streak after a successful send."""
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    state = _load_state(rd)
    state["consecutive_api_failures"] = 0
    state["last_success_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if draft_id is not None:
        _append_event(state, {"kind": "publish_ok", "draft_id": draft_id})
    _save_state(rd, state)


def transport_metrics_snapshot() -> dict[str, Any]:
    """Counters from in-process metrics + persisted production state."""
    snap = export_snapshot()
    counters = snap.get("counters") or snap
    rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    state = _load_state(rd)
    return {
        "telethon_flood_waits": int(counters.get("telethon_flood_waits") or 0),
        "telethon_reconnects": int(counters.get("telethon_reconnects") or 0),
        "telegram_api_failures": int(counters.get("telegram_api_failures") or 0),
        "polling_restarts_total": int(counters.get("polling_restarts_total") or 0),
        "telegram_network_failures_total": int(
            counters.get("telegram_network_failures_total") or 0
        ),
        "persisted": {
            "flood_wait_total": state.get("flood_wait_total"),
            "reconnect_total": state.get("reconnect_total"),
            "api_failure_total": state.get("api_failure_total"),
            "consecutive_api_failures": state.get("consecutive_api_failures"),
            "last_flood_wait_at": state.get("last_flood_wait_at"),
            "last_reconnect_at": state.get("last_reconnect_at"),
            "last_api_failure_at": state.get("last_api_failure_at"),
            "last_success_at": state.get("last_success_at"),
        },
        "recent_events": list(state.get("recent_events") or [])[-10:],
    }


def build_runtime_telegram_health(*, settings: Any | None = None) -> dict[str, Any]:
    """Read-only health from dependency snapshot (no live Bot API calls)."""
    from app.observability.ops_health import check_telegram_health
    from app.runtime.telegram_connectivity import build_telegram_connectivity_snapshot

    connectivity = build_telegram_connectivity_snapshot()
    component = check_telegram_health(settings)
    metrics = transport_metrics_snapshot()
    polling_retries = int(connectivity.get("polling_retry_count") or 0)
    flood_thresh = int(os.getenv("TELEGRAM_PROD_MAX_FLOOD_WAITS", "8"))
    reconnect_thresh = int(os.getenv("TELEGRAM_PROD_MAX_RECONNECTS", "12"))
    api_fail_thresh = int(os.getenv("TELEGRAM_PROD_MAX_API_FAILURES", "10"))

    blockers: list[str] = []
    if connectivity.get("conflict_detected"):
        blockers.append("telegram_conflict_detected")
    if connectivity.get("network_degraded"):
        blockers.append("telegram_network_degraded")
    if connectivity.get("collect_cycle", {}).get("collect_stalled"):
        blockers.append("collect_cycle_stalled")
    if int(metrics["telethon_flood_waits"]) > flood_thresh:
        blockers.append(f"flood_wait_high:{metrics['telethon_flood_waits']}")
    if int(metrics["telethon_reconnects"]) > reconnect_thresh:
        blockers.append(f"reconnect_high:{metrics['telethon_reconnects']}")
    if int(metrics["telegram_api_failures"]) > api_fail_thresh:
        blockers.append(f"api_failures_high:{metrics['telegram_api_failures']}")
    if not component.get("ok"):
        blockers.append("component_telegram_unhealthy")

    ok = not blockers and connectivity.get("bot_api_status") != "unhealthy"
    return {
        "ok": ok,
        "blockers": blockers,
        "connectivity": connectivity,
        "component_health": component,
        "transport_metrics": metrics,
        "polling_retry_count": polling_retries,
    }


async def run_live_production_connectivity(
    bot: "Bot",
    settings: "Settings",
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Live Bot API: token, channel post rights, operator chat, admin verification."""
    from bot.staging.telegram_connectivity import TelegramConnectivityCheck

    checker = TelegramConnectivityCheck(
        bot,
        digest_channel_id=getattr(settings, "target_channel_id", None),
        operator_chat_id=getattr(settings, "moderation_chat_id", None),
        publish_channel_id=getattr(settings, "target_channel_id", None),
    )
    report = await checker.run(strict=strict)
    rd = settings.runtime_state_dir
    state = _load_state(rd)
    state["last_connectivity_check_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["last_connectivity_ok"] = bool(report.passed)
    _save_state(rd, state)
    diag = report.structured_diagnostics()
    post_checks = [
        c for c in diag.get("checks", []) if str(c.get("name")) in ("digest", "publish")
    ]
    admin_ok = all(c.get("can_post") for c in post_checks) if post_checks else bool(
        report.publish_probe_ok
    )
    return {
        "ok": report.passed,
        "bot_ok": report.bot_ok,
        "bot_username": report.bot_username,
        "channel_permissions_ok": admin_ok,
        "bot_admin_verified": admin_ok and report.publish_probe_ok,
        "inline_keyboard_ok": report.inline_keyboard_ok,
        "publish_probe_ok": report.publish_probe_ok,
        "checks": diag.get("checks"),
        "errors": diag.get("errors"),
        "ready": diag.get("ready"),
    }


def evaluate_telegram_production_alerts(
    settings: Any,
    *,
    runtime_health: dict[str, Any] | None = None,
    live_check: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build alert payloads (enqueue via run_telegram_production_checks_and_alert)."""
    alerts: list[dict[str, Any]] = []
    health = runtime_health or build_runtime_telegram_health(settings=settings)
    metrics = health.get("transport_metrics") or transport_metrics_snapshot()
    streak = int((metrics.get("persisted") or {}).get("consecutive_api_failures") or 0)
    streak_thresh = int(os.getenv("TELEGRAM_PROD_ALERT_API_FAILURE_STREAK", "3"))

    if not health.get("ok"):
        alerts.append(
            _alert(
                kind="telegram_runtime_unhealthy",
                severity="critical",
                message=f"Telegram runtime unhealthy: {', '.join(health.get('blockers') or [])[:300]}",
                settings=settings,
                extra={"blockers": health.get("blockers")},
            )
        )

    if streak >= streak_thresh:
        alerts.append(
            _alert(
                kind="telegram_api_failure_streak",
                severity="critical",
                message=f"Telegram API failures streak={streak} (threshold {streak_thresh})",
                settings=settings,
                extra={"streak": streak, "metrics": metrics},
            )
        )

    flood_max = int(os.getenv("TELEGRAM_PROD_ALERT_FLOOD_WAITS", "5"))
    if int(metrics.get("telethon_flood_waits") or 0) >= flood_max:
        alerts.append(
            _alert(
                kind="telegram_flood_wait_burst",
                severity="warning",
                message=f"Telethon FloodWait count={metrics.get('telethon_flood_waits')} (threshold {flood_max})",
                settings=settings,
                extra={"metrics": metrics},
            )
        )

    reconnect_max = int(os.getenv("TELEGRAM_PROD_ALERT_RECONNECTS", "6"))
    if int(metrics.get("telethon_reconnects") or 0) >= reconnect_max:
        alerts.append(
            _alert(
                kind="telegram_reconnect_burst",
                severity="warning",
                message=f"Telegram reconnect count={metrics.get('telethon_reconnects')} (threshold {reconnect_max})",
                settings=settings,
                extra={"metrics": metrics},
            )
        )

    if live_check is not None and not live_check.get("ok"):
        alerts.append(
            _alert(
                kind="telegram_live_connectivity_failed",
                severity="critical",
                message="Live Telegram connectivity check failed (bot/channel/permissions)",
                settings=settings,
                extra=live_check,
            )
        )

    return alerts


def _alert(
    *,
    kind: str,
    severity: str,
    message: str,
    settings: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "message": message,
        "metrics": transport_metrics_snapshot(),
        "extra": extra or {},
        "suggested_actions": [
            "make ops-status",
            "review telegram_production_state.json",
            "docs/runbooks/production/TELEGRAM_FAILURE_RUNBOOK.md",
        ],
    }


async def run_telegram_production_checks_and_alert(
    settings: Any,
    bot: "Bot | None" = None,
    *,
    live_check: bool = False,
) -> dict[str, Any]:
    """Heartbeat hook: evaluate transport health and enqueue critical operator alerts."""
    runtime_health = build_runtime_telegram_health(settings=settings)
    live: dict[str, Any] | None = None
    if live_check and bot is not None:
        try:
            live = await run_live_production_connectivity(bot, settings)
        except Exception as exc:
            live = {"ok": False, "errors": [repr(exc)[:200]]}
    alerts = evaluate_telegram_production_alerts(
        settings,
        runtime_health=runtime_health,
        live_check=live,
    )

    for al in alerts:
        if al.get("severity") not in ("critical", "warning"):
            continue
        if al.get("severity") == "warning" and al.get("kind") not in (
            "telegram_flood_wait_burst",
            "telegram_reconnect_burst",
        ):
            continue
        from ops.operator_notifications import enqueue_operator_notification

        body = (
            f"{al['message']}\n"
            f"Actions: {', '.join(al.get('suggested_actions') or [])}"
        )
        enqueue_operator_notification(
            settings.runtime_state_dir,
            kind=str(al["kind"]),
            severity=str(al["severity"]),
            message=body[:400],
            fields=al,
            group_key=f"telegram_prod:{al['kind']}",
        )
        log_event(
            logger,
            "telegram_production.alert",
            kind=al["kind"],
            severity=al["severity"],
        )

    return {
        "runtime_health": runtime_health,
        "live_check": live,
        "alerts": alerts,
    }


def production_validation_report(settings: Any | None = None) -> dict[str, Any]:
    """Structured report for release checklist / CLI (sync, no Bot required)."""
    from app.config import load_settings

    s = settings or load_settings()
    health = build_runtime_telegram_health(settings=s)
    return {
        "ok": health.get("ok"),
        "blockers": health.get("blockers"),
        "connectivity_snapshot": health.get("connectivity"),
        "transport_metrics": health.get("transport_metrics"),
        "state_file": str(_state_path(s.runtime_state_dir)),
    }
