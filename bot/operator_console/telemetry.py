from __future__ import annotations

from typing import Any

from bot.runtime.state import runtime_state


def build_burnin_telemetry_summary(
    *,
    operations_platform: Any,
    mesh_health: float,
    open_contradictions: int,
    misinfo_alerts: int = 0,
    storage_growth_mb: float = 0.0,
    amplification: float = 0.0,
) -> dict[str, Any]:
    interventions = 0
    if operations_platform is not None:
        interventions = operations_platform.repository.operator_intervention_count()
    replay_lag = "healthy"
    if operations_platform is not None:
        health = operations_platform.replay.measure_replay_health()
        if health.reconstruction_latency_ms > 3000:
            replay_lag = f"slow ({health.reconstruction_latency_ms:.0f}ms)"
    return {
        "ingested_session": runtime_state.published_count + runtime_state.skipped_count,
        "replay_lag": replay_lag,
        "open_contradictions": open_contradictions,
        "misinfo_alerts": misinfo_alerts,
        "mesh_health": mesh_health,
        "storage_growth_mb": storage_growth_mb,
        "amplification": amplification,
        "operator_interventions": interventions,
    }
