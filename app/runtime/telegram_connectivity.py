"""Aggregated Telegram transport health for /health and operator CLI."""

from __future__ import annotations

import time
from typing import Any

from app.dependency_state import DependencyStatus, get_dependency_state
from app.runtime.collect_cycle_guard import check_stall, collect_timeout_sec, snapshot as collect_snap
from app.runtime_activity import activity_snapshot, seconds_since_collect


def build_telegram_connectivity_snapshot() -> dict[str, Any]:
    deps = get_dependency_state()
    tg = deps.telegram_api.to_dict()
    activity = activity_snapshot()
    collect = collect_snap()
    if collect.get("collect_in_progress"):
        check_stall()

    polling_degraded = deps.telegram_api.status != DependencyStatus.HEALTHY
    telethon_dep = deps.telethon.to_dict() if hasattr(deps, "telethon") else {}
    telethon_ok = telethon_dep.get("status") == DependencyStatus.HEALTHY.value

    since_collect = seconds_since_collect()
    dc_reachable: bool | None = None
    if collect.get("collect_stalled"):
        dc_reachable = False
    elif telethon_ok and since_collect is not None and since_collect < 3600:
        dc_reachable = True
    elif deps.collector_enabled and not collect.get("collect_in_progress"):
        dc_reachable = telethon_ok

    return {
        "bot_api_status": tg.get("status"),
        "bot_api_detail": (tg.get("detail") or "")[:200],
        "polling_active": tg.get("polling_active", deps.polling_active),
        "polling_retry_count": tg.get("retry_count", deps.polling_retry_count),
        "conflict_detected": tg.get("conflict_detected", deps.conflict_detected),
        "telethon_status": telethon_dep.get("status"),
        "collector_enabled": deps.collector_enabled,
        "dc_reachable": dc_reachable,
        "network_degraded": polling_degraded or not telethon_ok,
        "last_successful_collect_at": activity.get("last_successful_collect_at"),
        "last_successful_publish_at": activity.get("last_successful_publish_at"),
        "last_collect_failure_at": activity.get("last_collect_failure_at"),
        "seconds_since_collect": activity.get("seconds_since_collect"),
        "seconds_since_publish": activity.get("seconds_since_publish"),
        "collect_cycle": collect,
        "collect_timeout_sec": collect_timeout_sec(),
        "async_integrity_ok": True,
    }
