from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from bot.operations.runtime import OperationsPlatform
from bot.reliability.burnin_mode import BurnInDiagnosticsRunner
from bot.reliability.daily_report import format_daily_operational_report
from bot.reliability.incident_manager import ProductionIncidentManager
from bot.reliability.metrics_aggregator import MetricsAggregator
from bot.reliability.publish_gate import PublishGateController
from bot.reliability.runtime_health_manager import RuntimeHealthManager
from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import HealthState, IncidentSeverity, SubsystemName
from bot.reliability.watchdog_recovery import SubsystemWatchdog
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


@dataclass
class ReliabilityTickResult:
    health: dict[str, Any]
    recovery: list[dict[str, Any]]
    publish_gate: str
    burnin: dict[str, Any] | None = None


class ReliabilityCoordinator:
    """Production reliability facade — single tick for health, recovery, incidents."""

    def __init__(
        self,
        *,
        settings: ReliabilitySettings,
        health: RuntimeHealthManager,
        watchdog: SubsystemWatchdog,
        incidents: ProductionIncidentManager,
        publish_gate: PublishGateController,
        metrics: MetricsAggregator,
        burnin: BurnInDiagnosticsRunner | None = None,
    ) -> None:
        self.settings = settings
        self.health = health
        self.watchdog = watchdog
        self.incidents = incidents
        self.publish_gate = publish_gate
        self.metrics = metrics
        self.burnin = burnin or BurnInDiagnosticsRunner()
        self._last_daily_report = 0.0
        self._subsystem_uptime: dict[str, float] = {}

    async def tick(
        self,
        *,
        operations: OperationsPlatform | None,
        registry: Any,
        ops_report: dict[str, Any],
        signals: dict[str, Any],
    ) -> ReliabilityTickResult:
        if registry is not None:
            self.health.ingest_from_registry(registry)

        self.health.heartbeat(
            SubsystemName.COGNITION,
            ok=signals.get("mesh_health", 1.0) > 0.5,
            latency_ms=float(signals.get("cognition_latency_ms", 0)),
            detail=f"mesh={signals.get('mesh_health', 1.0):.2f}",
        )
        self.health.heartbeat(
            SubsystemName.PUBLISH,
            ok=int(signals.get("queue_backlog", 0)) < self.settings.publish_max_queue_depth,
            detail=f"backlog={signals.get('queue_backlog', 0)}",
        )
        self.health.heartbeat(
            SubsystemName.OPENAI_API,
            ok=float(signals.get("openai_failure_rate", 0)) < 0.2,
            detail="openai_ok",
        )

        snap = self.health.probe()
        try:
            from bot.observability.metrics import set_reliability_degraded, set_reliability_open_incidents

            set_reliability_degraded(snap.degraded_mode)
            open_count = len(operations.repository.list_incidents(status="open", limit=50)) if operations else 0
            set_reliability_open_incidents(open_count)
        except Exception:
            pass

        for sub in snap.subsystems:
            key = sub.name.value
            prev = self._subsystem_uptime.get(key, 100.0)
            if sub.state == HealthState.HEALTHY:
                self._subsystem_uptime[key] = min(100.0, prev + 0.5)
            else:
                self._subsystem_uptime[key] = max(0.0, prev - 2.0)

        stalled = list(ops_report.get("stalled_loops", []))
        recoveries = await self.watchdog.evaluate(
            stalled_loops=stalled,
            queue_backlog=snap.queue_depth,
            health_state=snap.overall_state,
            telegram_failures=int(signals.get("telegram_failures_6h", 0)),
            openai_timeouts=int(signals.get("openai_timeouts", 0)),
        )

        if snap.overall_state in (HealthState.CRITICAL, HealthState.FAILED):
            await self.incidents.emit(
                title=f"Runtime {snap.overall_state.value}",
                severity=IncidentSeverity.CRITICAL,
                subsystem="runtime",
                summary=f"health_score={snap.health_score:.2f} queue={snap.queue_depth}",
                correlation_key="runtime:health",
                recovery_status=f"recoveries={len(recoveries)}",
            )

        fatal_recent = self.incidents.recent_fatal_count()
        gate = self.publish_gate.evaluate(
            health_state=snap.overall_state,
            health_score=snap.health_score,
            queue_depth=snap.queue_depth,
            cognition_latency_ms=float(signals.get("cognition_latency_ms", 0)),
            telegram_failure_rate=float(signals.get("telegram_failure_rate_6h", 0)),
            fatal_incidents_recent=fatal_recent,
        )
        if snap.degraded_mode:
            runtime_state.operational_mode = "degraded"
        elif snap.overall_state == HealthState.HEALTHY:
            runtime_state.operational_mode = "normal"

        burnin_out: dict[str, Any] | None = None
        if self.settings.burnin_mode:
            self.burnin.record_queue(snap.queue_depth)
            diag = self.burnin.run(
                health_score=snap.health_score,
                stalled_loops=stalled,
                ops_report=ops_report,
            )
            burnin_out = {
                "reliability_score": diag.reliability_score,
                "memory_rss_mb": diag.memory_rss_mb,
            }

        now = time.monotonic()
        if now - self._last_daily_report >= self.settings.daily_report_interval_sec:
            self._last_daily_report = now
            ops_report["daily_report_pending"] = True

        return ReliabilityTickResult(
            health=snap.to_dict(),
            recovery=[{"subsystem": r.subsystem, "action": r.action, "ok": r.success} for r in recoveries],
            publish_gate=gate.summary(),
            burnin=burnin_out,
        )

    async def maybe_send_daily_report(self, *, notify: Any) -> str | None:
        agg = self.metrics.aggregate(health=self.health.last_snapshot)
        rows = self.incidents._lifecycle.list_open(limit=8)
        summaries = [f"{r.get('severity')}: {r.get('title', '')[:50]}" for r in rows]
        text = format_daily_operational_report(
            metrics=agg,
            health=self.health.last_snapshot,
            incident_summaries=summaries,
            subsystem_uptime=self._subsystem_uptime,
        )
        if notify is not None:
            await notify(text)
        return text
