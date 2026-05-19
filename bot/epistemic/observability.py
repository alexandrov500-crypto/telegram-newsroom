from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.epistemic.repository import EpistemicRepository


@dataclass
class EpistemicObservabilitySnapshot:
    confidence_heatmap: dict[str, float] = field(default_factory=dict)
    contradiction_network: list[dict] = field(default_factory=list)
    trust_evolution: list[dict] = field(default_factory=list)
    narrative_pressure: dict[str, Any] = field(default_factory=dict)
    misinformation_pressure: float = 0.0
    drift_timeline: list[dict] = field(default_factory=list)
    federation_stability: float = 1.0


class EpistemicObservability:
    """Integrity observability for Grafana and operator inspection."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    def build_snapshot(
        self,
        *,
        regional_confidence: dict[str, float] | None = None,
        mesh_health: float = 1.0,
    ) -> EpistemicObservabilitySnapshot:
        contradictions = self._repo.open_contradictions(limit=15)
        with self._repo._connect() as conn:
            alerts = conn.execute(
                """
                SELECT alert_type, severity FROM epistemic_alerts
                WHERE status = 'pending_review' ORDER BY severity DESC LIMIT 10
                """
            ).fetchall()
            drift_rows = conn.execute(
                """
                SELECT drift_kind, entropy_score, diversity_score, created_at
                FROM epistemic_drift_samples ORDER BY created_at DESC LIMIT 10
                """
            ).fetchall()
            trust_rows = conn.execute(
                """
                SELECT from_node, to_node, trust_score, reason FROM epistemic_trust_edges
                ORDER BY updated_at DESC LIMIT 12
                """
            ).fetchall()

        misinfo_pressure = sum(float(a["severity"]) for a in alerts) / max(len(alerts), 1)

        snap = EpistemicObservabilitySnapshot(
            confidence_heatmap=regional_confidence or {},
            contradiction_network=[
                {"id": c["contradiction_id"], "severity": c["severity"], "subject": c["subject_type"]}
                for c in contradictions
            ],
            trust_evolution=[dict(r) for r in trust_rows],
            narrative_pressure={"open_contradictions": len(contradictions)},
            misinformation_pressure=round(misinfo_pressure, 4),
            drift_timeline=[dict(r) for r in drift_rows],
            federation_stability=round(mesh_health * (1.0 - misinfo_pressure * 0.3), 4),
        )
        self._repo.save_observability_snapshot(
            "integrity_full",
            {
                "heatmap": snap.confidence_heatmap,
                "contradictions": len(snap.contradiction_network),
                "misinfo_pressure": snap.misinformation_pressure,
                "federation_stability": snap.federation_stability,
            },
        )
        try:
            from bot.observability.metrics import (
                set_epistemic_stability,
                set_misinformation_pressure,
            )

            set_epistemic_stability(snap.federation_stability)
            set_misinformation_pressure(snap.misinformation_pressure)
        except Exception:
            pass
        return snap
