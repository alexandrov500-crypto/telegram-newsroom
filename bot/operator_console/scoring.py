from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpsHealthScore:
    overall: float
    ingestion: float
    cognition: float
    epistemic: float
    federation: float
    replay: float
    operator_load: float
    trend: str
    components: dict[str, float]

    def summary_text(self) -> str:
        lines = [
            "<b>📊 Ops health score</b>",
            f"Overall: <b>{self.overall:.2f}</b> ({self.trend})",
            "",
            f"Ingestion: {self.ingestion:.2f}",
            f"Cognition: {self.cognition:.2f}",
            f"Epistemic: {self.epistemic:.2f}",
            f"Federation: {self.federation:.2f}",
            f"Replay: {self.replay:.2f}",
            f"Operator load: {self.operator_load:.2f}",
        ]
        return "\n".join(lines)


def compute_ops_health(
    *,
    queue_backlog: int = 0,
    mesh_health: float = 1.0,
    epistemic_stability: float = 1.0,
    open_contradictions: int = 0,
    replay_divergence: float = 0.0,
    fatigue_score: float = 0.0,
    feed_reliability_mean: float = 0.8,
) -> OpsHealthScore:
    ingestion = max(0.0, min(1.0, 1.0 - queue_backlog / 2000.0)) * 0.7 + feed_reliability_mean * 0.3
    cognition = max(0.0, min(1.0, epistemic_stability * 0.85 + mesh_health * 0.15))
    epistemic = max(
        0.0,
        min(1.0, epistemic_stability - open_contradictions / 80.0),
    )
    federation = max(0.0, min(1.0, mesh_health))
    replay = max(0.0, min(1.0, 1.0 - replay_divergence * 2))
    operator_load = max(0.0, min(1.0, 1.0 - fatigue_score))
    overall = round(
        0.2 * ingestion
        + 0.15 * cognition
        + 0.25 * epistemic
        + 0.15 * federation
        + 0.15 * replay
        + 0.1 * operator_load,
        3,
    )
    trend = "stable"
    if overall < 0.55:
        trend = "degrading"
    elif overall > 0.82:
        trend = "healthy"
    return OpsHealthScore(
        overall=overall,
        ingestion=round(ingestion, 3),
        cognition=round(cognition, 3),
        epistemic=round(epistemic, 3),
        federation=round(federation, 3),
        replay=round(replay, 3),
        operator_load=round(operator_load, 3),
        trend=trend,
        components={
            "backlog": float(queue_backlog),
            "contradictions": float(open_contradictions),
            "mesh": mesh_health,
        },
    )
