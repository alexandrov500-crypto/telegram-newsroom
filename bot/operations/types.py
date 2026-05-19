from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BurnInProfile:
    name: str
    duration_hours: float
    sample_interval_sec: int = 300


BURNIN_PROFILES = {
    "24h": BurnInProfile("24h", 24.0),
    "7d": BurnInProfile("7d", 168.0),
    "30d": BurnInProfile("30d", 720.0),
}


@dataclass
class ProductionSLOs:
    """Operational and epistemic SLO targets for certification."""

    queue_backlog_max: int = 500
    epistemic_stability_min: float = 0.65
    mesh_health_min: float = 0.6
    replay_divergence_max: float = 0.15
    misinfo_false_positive_max: float = 0.25
    openai_daily_budget_usd: float = 50.0
    storage_growth_mb_per_day_max: float = 200.0
    operator_alert_fatigue_per_hour_max: int = 12

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_backlog_max": self.queue_backlog_max,
            "epistemic_stability_min": self.epistemic_stability_min,
            "mesh_health_min": self.mesh_health_min,
            "replay_divergence_max": self.replay_divergence_max,
            "misinfo_false_positive_max": self.misinfo_false_positive_max,
            "openai_daily_budget_usd": self.openai_daily_budget_usd,
            "storage_growth_mb_per_day_max": self.storage_growth_mb_per_day_max,
            "operator_alert_fatigue_per_hour_max": self.operator_alert_fatigue_per_hour_max,
        }


@dataclass(frozen=True)
class CertificationGate:
    gate_id: str
    name: str
    passed: bool
    detail: str
    value: float | None = None
    threshold: float | None = None


@dataclass
class CertificationReport:
    run_id: str
    passed: bool
    gates: list[CertificationGate] = field(default_factory=list)
    summary: str = ""
