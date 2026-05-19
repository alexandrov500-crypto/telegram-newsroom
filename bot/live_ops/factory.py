from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from bot.live_ops.coordinator import LiveOpsCoordinator
from bot.live_ops.event_bus import NewsroomLiveEventBus
from bot.live_ops.observability.telemetry import LiveOpsTelemetry
from bot.live_ops.recovery.disaster_recovery import DisasterRecoveryManager
from bot.live_ops.settings import LiveOpsSettings
from bot.live_ops.stability.long_run import LongRunStabilityTracker
from bot.live_ops.storage.abstraction import resolve_storage_stack
from bot.live_ops.tenancy.scope import TenantRegistry
from bot.live_ops.cognition.evolution import CognitionEvolutionOrchestrator
from bot.live_ops.workers.topology import WorkerMeshRegistry


def build_live_ops_stack(
    db_path: Path,
    *,
    stream_bus: Any | None = None,
    inprocess_bus: Any | None = None,
    node_id: str | None = None,
) -> LiveOpsCoordinator:
    settings = LiveOpsSettings.from_env()
    if node_id:
        settings = replace(settings, node_id=node_id)
    telemetry = LiveOpsTelemetry()
    bus = NewsroomLiveEventBus(
        stream_bus=stream_bus if settings.event_bus_enabled else None,
        inprocess_bus=inprocess_bus,
        telemetry=telemetry,
    )
    storage = resolve_storage_stack(db_path)
    return LiveOpsCoordinator(
        settings=settings,
        event_bus=bus,
        recovery=DisasterRecoveryManager(db_path=db_path),
        workers=WorkerMeshRegistry(),
        stability=LongRunStabilityTracker(),
        tenants=TenantRegistry(),
        cognition=CognitionEvolutionOrchestrator(),
        telemetry=telemetry,
        storage=storage,
    )
