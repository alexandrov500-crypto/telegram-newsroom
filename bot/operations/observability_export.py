from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OperationalIntelligenceExport:
    """JSON export bundle for Grafana / external ops tools."""

    topology_replay: dict[str, Any] = field(default_factory=dict)
    cognition_lineage: list[dict] = field(default_factory=list)
    contradiction_network: list[dict] = field(default_factory=list)
    replay_timeline: list[dict] = field(default_factory=list)
    narrative_drift: list[dict] = field(default_factory=list)
    federation_pressure: dict[str, float] = field(default_factory=dict)
    operator_timeline: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "topology_replay": self.topology_replay,
                "cognition_lineage": self.cognition_lineage,
                "contradiction_network": self.contradiction_network,
                "replay_timeline": self.replay_timeline,
                "narrative_drift": self.narrative_drift,
                "federation_pressure": self.federation_pressure,
                "operator_timeline": self.operator_timeline,
            },
            indent=2,
        )


class ObservabilityPlatform:
    """Operational intelligence exports — explainability-first data surfaces."""

    def build_export(
        self,
        *,
        mesh_report: dict | None = None,
        epistemic_snap: dict | None = None,
        contradictions: list[dict] | None = None,
        burnin_samples: list[dict] | None = None,
        operator_alerts: list[dict] | None = None,
    ) -> OperationalIntelligenceExport:
        export = OperationalIntelligenceExport()
        if mesh_report:
            export.topology_replay = {
                "health": mesh_report.get("mesh_health"),
                "recommendations": mesh_report.get("recommendations", []),
            }
            export.federation_pressure = mesh_report.get("pressure_balance") or {}
        if epistemic_snap:
            export.cognition_lineage = [
                {"type": "epistemic", "stability": epistemic_snap.get("federation_stability")},
            ]
            export.narrative_drift = epistemic_snap.get("drift_timeline", [])
        if contradictions:
            export.contradiction_network = [
                {"id": c.get("contradiction_id"), "severity": c.get("severity")} for c in contradictions
            ]
        if burnin_samples:
            export.replay_timeline = burnin_samples[:50]
        if operator_alerts:
            export.operator_timeline = [
                {"title": a.get("title"), "category": a.get("category")} for a in operator_alerts
            ]
        return export
