from __future__ import annotations

from typing import Any, Callable

from bot.operations.runtime import OperationsPlatform
from bot.reliability.coordinator import ReliabilityCoordinator
from bot.reliability.incident_manager import ProductionIncidentManager
from bot.reliability.metrics_aggregator import MetricsAggregator
from bot.reliability.publish_gate import PublishGateController
from bot.reliability.runtime_health_manager import RuntimeHealthManager
from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import IncidentSeverity, PublishMode
from bot.reliability.watchdog_recovery import SubsystemWatchdog
from bot.runtime.state import runtime_state


def build_reliability_stack(
    operations: OperationsPlatform,
    *,
    queue_depth_fn: Callable[[], int],
    operator_notify: Any | None = None,
) -> ReliabilityCoordinator:
    settings = ReliabilitySettings.from_env()
    publish_gate = PublishGateController(settings)
    mode = publish_gate.current_mode()
    runtime_state.dry_run_mode = mode == PublishMode.DRY_RUN
    if mode == PublishMode.SHADOW:
        runtime_state.shadow_publish_only = True

    health = RuntimeHealthManager(
        settings,
        queue_depth_fn=queue_depth_fn,
        publish_mode_fn=publish_gate.current_mode,
        startup_time=runtime_state.startup_time,
    )
    incidents = ProductionIncidentManager(operations.incidents, operations.repository)
    watchdog = SubsystemWatchdog(settings)
    metrics = MetricsAggregator(operations.repository)
    coord = ReliabilityCoordinator(
        settings=settings,
        health=health,
        watchdog=watchdog,
        incidents=incidents,
        publish_gate=publish_gate,
        metrics=metrics,
    )

    async def _on_incident(
        *,
        title: str,
        severity: str,
        subsystem: str,
        detail: str,
        correlation_key: str,
        recovery_status: str = "none",
    ) -> None:
        await incidents.emit(
            title=title,
            severity=severity,
            subsystem=subsystem,
            summary=title,
            detail=detail,
            correlation_key=correlation_key,
            recovery_status=recovery_status,
        )

    watchdog._on_incident = _on_incident

    if operator_notify is not None:

        async def _telegram_notify(inc: Any) -> None:
            text = incidents.format_telegram_alert(inc)
            if inc.severity.rank >= IncidentSeverity.ERROR.rank:
                await operator_notify(
                    text,
                    severity=inc.severity,
                    pinned=inc.severity == IncidentSeverity.FATAL,
                )
            if inc.severity == IncidentSeverity.FATAL:
                runtime_state.ingestion_paused = True

        incidents.on_notify(_telegram_notify)

    return coord
