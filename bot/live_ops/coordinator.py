from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from bot.live_ops.cognition.evolution import CognitionEvolutionOrchestrator
from bot.live_ops.event_bus import NewsroomLiveEventBus
from bot.live_ops.observability.telemetry import LiveOpsTelemetry
from bot.live_ops.recovery.disaster_recovery import DisasterRecoveryManager, RecoveryReport
from bot.live_ops.settings import LiveOpsSettings
from bot.live_ops.stability.long_run import LongRunStabilityTracker
from bot.live_ops.tenancy.scope import ChannelScope, TenantRegistry
from bot.live_ops.workers.topology import WorkerMeshRegistry, WorkerRole

logger = logging.getLogger(__name__)


@dataclass
class LiveOpsSnapshot:
    stability_score: float
    stability_forecast: str
    event_bus_pending: int
    event_bus_dlq: int
    worker_count: int
    stale_workers: int
    storage_primary: str
    storage_primary_ok: bool
    recovery_mode: bool
    tenants: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stability_score": self.stability_score,
            "stability_forecast": self.stability_forecast,
            "event_bus_pending": self.event_bus_pending,
            "event_bus_dlq": self.event_bus_dlq,
            "worker_count": self.worker_count,
            "stale_workers": self.stale_workers,
            "storage_primary": self.storage_primary,
            "storage_primary_ok": self.storage_primary_ok,
            "recovery_mode": self.recovery_mode,
            "tenants": list(self.tenants),
        }


@dataclass
class LiveOpsCoordinator:
    """Final live operations facade: bus, workers, recovery, stability, tenancy."""

    settings: LiveOpsSettings
    event_bus: NewsroomLiveEventBus
    recovery: DisasterRecoveryManager
    workers: WorkerMeshRegistry
    stability: LongRunStabilityTracker
    tenants: TenantRegistry
    cognition: CognitionEvolutionOrchestrator
    telemetry: LiveOpsTelemetry = field(default_factory=LiveOpsTelemetry)
    storage: dict[str, Any] = field(default_factory=dict)
    _recovery_report: RecoveryReport | None = None
    _queue_depth_fn: Callable[[], int] | None = None
    _last_tick: float = field(default_factory=time.monotonic)

    async def startup(self) -> RecoveryReport:
        self._register_local_workers()
        if self.settings.recovery_on_startup or self.recovery.recovery_mode:
            self._recovery_report = await self.recovery.run_startup_recovery(
                event_bus=self.event_bus,
            )
        return self._recovery_report or RecoveryReport(
            mode="NORMAL",
            passed=True,
            replayed_events=0,
            queue_depth=0,
            issues=(),
        )

    def _register_local_workers(self) -> None:
        if not self.settings.worker_mesh_enabled:
            return
        nid = self.settings.node_id
        for role, queues in (
            (WorkerRole.INGEST, ("ingest",)),
            (WorkerRole.COGNITION, ("cognition",)),
            (WorkerRole.PUBLISH, ("publish",)),
            (WorkerRole.OPERATOR, ("operator",)),
            (WorkerRole.METRICS, ("metrics",)),
            (WorkerRole.RECOVERY, ("recovery",)),
        ):
            self.workers.register(role, nid, queues=queues)
            self.workers.heartbeat(role, nid)

    async def tick(
        self,
        *,
        queue_depth: int = 0,
        token_spend_hour: float = 0.0,
        event_loop_lag_ms: float = 0.0,
    ) -> LiveOpsSnapshot:
        self._last_tick = time.monotonic()
        if self.settings.worker_mesh_enabled:
            for w in self.workers.snapshot():
                self.workers.heartbeat(WorkerRole(w["role"]), w["node_id"])
        score = 1.0
        forecast = "stable"
        if self.settings.stability_tracking:
            score = self.stability.record(
                queue_depth=queue_depth,
                token_spend_hour=token_spend_hour,
                event_loop_lag_ms=event_loop_lag_ms,
            )
            forecast = self.stability.drift_forecast()
        primary = self.storage.get("primary")
        return LiveOpsSnapshot(
            stability_score=score,
            stability_forecast=forecast,
            event_bus_pending=self.event_bus.pending_count,
            event_bus_dlq=self.event_bus.dead_letter_count,
            worker_count=len(self.workers.snapshot()),
            stale_workers=len(self.workers.stale_workers()),
            storage_primary=primary.backend_name() if primary else "unknown",
            storage_primary_ok=bool(self.storage.get("primary_ok")),
            recovery_mode=self.recovery.recovery_mode,
            tenants=tuple(self.tenants.list_tenants()),
        )

    def go_live_readiness(
        self,
        *,
        reliability_score: float | None = None,
        safety_ok: bool = True,
        queue_depth: int = 0,
    ) -> dict[str, Any]:
        snap = LiveOpsSnapshot(
            stability_score=self.stability.rolling_score(),
            stability_forecast=self.stability.drift_forecast(),
            event_bus_pending=self.event_bus.pending_count,
            event_bus_dlq=self.event_bus.dead_letter_count,
            worker_count=len(self.workers.snapshot()),
            stale_workers=len(self.workers.stale_workers()),
            storage_primary=(
                self.storage["primary"].backend_name()
                if self.storage.get("primary")
                else "sqlite"
            ),
            storage_primary_ok=bool(self.storage.get("primary_ok", True)),
            recovery_mode=self.recovery.recovery_mode,
            tenants=tuple(self.tenants.list_tenants()),
        )
        blockers: list[str] = []
        if snap.event_bus_dlq > 50:
            blockers.append("event_bus_dlq_high")
        if snap.stale_workers > 0:
            blockers.append("stale_workers")
        if queue_depth > 500:
            blockers.append("queue_pressure")
        if not safety_ok:
            blockers.append("production_safety")
        if reliability_score is not None and reliability_score < 0.6:
            blockers.append("reliability_low")
        if snap.stability_score < 0.65:
            blockers.append("stability_degraded")
        ready = len(blockers) == 0
        return {
            "ready": ready,
            "blockers": blockers,
            "snapshot": snap.to_dict(),
        }

    def register_channel(self, channel_id: int, **kwargs: Any) -> ChannelScope:
        scope = ChannelScope(channel_id=channel_id, **kwargs)
        self.tenants.register(scope)
        return scope

    @property
    def recovery_report(self) -> RecoveryReport | None:
        return self._recovery_report
