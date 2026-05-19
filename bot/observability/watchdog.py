from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from bot.observability.alerts import AlertManager
from bot.observability.logging_setup import get_logger
from bot.observability.loop_diagnostics import collect_lag_context, record_event_loop_lag
from bot.observability.metrics import (
    observe_event_loop_lag,
    set_process_memory_mb,
)
from bot.observability.registry import ObservabilityRegistry

logger = get_logger(__name__)


class BurnInWatchdog:
    """Low-overhead supervisor for 24/7 burn-in operation."""

    def __init__(
        self,
        registry: ObservabilityRegistry,
        alerts: AlertManager | None,
        *,
        interval_sec: int = 30,
        queue_backlog_threshold: int = 200,
        rss_stall_sec: int = 600,
        event_loop_stall_sec: float = 2.0,
    ) -> None:
        self._registry = registry
        self._alerts = alerts
        self._interval_sec = interval_sec
        self._queue_threshold = queue_backlog_threshold
        self._rss_stall_sec = rss_stall_sec
        self._event_loop_stall_sec = event_loop_stall_sec
        self._running = False

    async def run(self) -> None:
        self._running = True
        logger.info("event=watchdog_started", interval_sec=self._interval_sec)
        try:
            while self._running:
                await self._probe_once()
                await asyncio.sleep(self._interval_sec)
        except asyncio.CancelledError:
            raise
        finally:
            self._running = False
            logger.info("event=watchdog_stopped")

    def stop(self) -> None:
        self._running = False

    async def _probe_once(self) -> None:
        lag = await self._measure_event_loop_lag()
        await self._registry.mark_event_loop_probe(lag)
        observe_event_loop_lag(lag)
        record_event_loop_lag(lag)

        try:
            import resource

            rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS reports bytes; Linux reports kilobytes
            if rss_bytes > 10_000_000:
                mb = rss_bytes / (1024 * 1024)
            else:
                mb = rss_bytes / 1024
            set_process_memory_mb(mb)
        except Exception:
            pass

        backlog = self._registry.queue_backlog()
        now = datetime.now(timezone.utc)

        if backlog >= self._queue_threshold and self._alerts is not None:
            await self._alerts.warning(
                "Editorial queue backlog high",
                details={"queue_backlog": backlog, "threshold": self._queue_threshold},
            )

        if lag >= self._event_loop_stall_sec:
            ctx = collect_lag_context()
            logger.critical(
                "event=event_loop_lag_detected %s",
                ctx,
            )
            if self._alerts is not None:
                await self._alerts.critical(
                    "Event loop lag detected",
                    details=ctx,
                )

        async with self._registry._lock:
            last_rss = self._registry.last_rss_cycle_at
            rss_enabled = self._registry.rss_ingestion_running

        if rss_enabled and last_rss is not None:
            if now - last_rss > timedelta(seconds=self._rss_stall_sec):
                if self._alerts is not None:
                    await self._alerts.warning(
                        "RSS ingestion appears stalled",
                        details={"last_cycle": last_rss.isoformat()},
                    )

        try:
            from bot.observability.loop_registry import get_loop_registry
            from bot.observability.runtime_degradation import evaluate_soft_degradation
            from bot.operations.runtime_supervisor import RuntimeSupervisor

            evaluate_soft_degradation()
            loop_reg = get_loop_registry()
            stalled_names = loop_reg.watchdog_stalled_names()
            if stalled_names and self._alerts is not None:
                try:
                    from bot.ops_forensics.hooks import record_timeline

                    record_timeline(
                        "watchdog_alert",
                        severity="warning",
                        details={"title": "Background loops stalled", "loops": stalled_names},
                    )
                except Exception:
                    pass
                await self._alerts.warning(
                    "Background loops stalled",
                    details={"loops": stalled_names},
                )

            supervisor = RuntimeSupervisor(queue_backlog_fn=self._registry.queue_backlog)
            report = await supervisor.probe()
            if report.recovery_actions:
                await supervisor.attempt_recovery(report)
                self._registry.watchdog_restarts += len(report.recovery_actions)
        except Exception:
            pass

    @staticmethod
    async def _measure_event_loop_lag() -> float:
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        marker = loop.time()

        async def _wake() -> None:
            await asyncio.sleep(0)

        await _wake()
        _ = marker
        return time.perf_counter() - started
