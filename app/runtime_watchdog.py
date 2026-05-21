"""Lightweight long-running stability watchdog (logs only, no process exit)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.runtime_activity import (
    exception_count_in_window,
    record_pipeline_exception,
    seconds_since_collect,
    seconds_since_scheduler_tick,
)
from app.runtime_lifecycle import emit_lifecycle
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_last_loop_lag_mono = 0.0


def reset_watchdog_for_tests() -> None:
    global _last_loop_lag_mono
    _last_loop_lag_mono = 0.0


def note_pipeline_exception() -> None:
    record_pipeline_exception()


async def measure_event_loop_lag_sec() -> float:
    """Schedule a callback and measure scheduling delay (proxy for loop lag)."""
    loop = asyncio.get_running_loop()
    t0 = loop.time()

    async def _probe() -> None:
        nonlocal t0
        return

    await asyncio.sleep(0)
    scheduled = loop.time()
    await asyncio.sleep(0.001)
    after = loop.time()
    return max(0.0, after - scheduled)


async def run_watchdog_checks(settings: Any, *, collector_enabled: bool) -> None:
    """Non-fatal operational warnings for soak / production observability."""
    global _last_loop_lag_mono
    interval_min = max(1, int(getattr(settings, "pipeline_interval_minutes", 15)))
    stall_mult = max(1.5, float(getattr(settings, "watchdog_scheduler_stall_multiplier", 2.5)))
    collector_mult = max(1.5, float(getattr(settings, "watchdog_collector_stall_multiplier", 2.5)))
    burst_n = max(3, int(getattr(settings, "watchdog_exception_burst_count", 10)))
    burst_window = max(30.0, float(getattr(settings, "watchdog_exception_burst_window_sec", 300.0)))
    lag_warn = max(0.5, float(getattr(settings, "watchdog_event_loop_lag_warn_sec", 2.0)))

    stall_sec = interval_min * 60.0 * stall_mult
    since_tick = seconds_since_scheduler_tick()
    from ops.incidents.triggers import note_watchdog_alert

    if since_tick is not None and since_tick > stall_sec:
        fields = {
            "since_last_tick_sec": round(since_tick, 1),
            "threshold_sec": stall_sec,
        }
        emit_lifecycle("watchdog.scheduler.stalled", **fields)
        log_event(
            logger,
            "watchdog.scheduler.stalled",
            recovery="check_apscheduler_and_pipeline_lock",
            subsystem="watchdog",
            **fields,
        )
        note_watchdog_alert(settings, "scheduler.stalled", fields=fields)

    if collector_enabled:
        collect_stall = interval_min * 60.0 * collector_mult
        since_collect = seconds_since_collect()
        if since_collect is not None and since_collect > collect_stall:
            fields = {
                "since_last_collect_sec": round(since_collect, 1),
                "threshold_sec": collect_stall,
            }
            log_event(
                logger,
                "watchdog.collector.stalled",
                recovery="check_telethon_session_and_channels",
                subsystem="watchdog",
                **fields,
            )
            note_watchdog_alert(settings, "collector.stalled", fields=fields)

    burst = exception_count_in_window(burst_window)
    if burst >= burst_n:
        fields = {"count": burst, "window_sec": burst_window, "threshold": burst_n}
        log_event(
            logger,
            "watchdog.exception_burst",
            recovery="inspect_recent_pipeline_inner_failed_logs",
            subsystem="watchdog",
            **fields,
        )
        note_watchdog_alert(settings, "exception_burst", fields=fields)

    try:
        lag = await measure_event_loop_lag_sec()
        if lag >= lag_warn and (time.monotonic() - _last_loop_lag_mono) > 60.0:
            _last_loop_lag_mono = time.monotonic()
            fields = {"lag_sec": round(lag, 4), "threshold_sec": lag_warn}
            log_event(
                logger,
                "watchdog.event_loop.lag",
                recovery="reduce_tick_work_or_scale_host",
                subsystem="watchdog",
                **fields,
            )
            note_watchdog_alert(settings, "event_loop.lag", fields=fields)
    except Exception as exc:
        log_event(logger, "watchdog.event_loop.probe_failed", error=repr(exc), subsystem="watchdog")
