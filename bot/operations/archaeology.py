from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class IncidentBundle:
    bundle_id: str
    incident_key: str
    timeline: list[dict[str, Any]]
    cognitive_state: dict[str, Any]
    topology: dict[str, Any]
    governance_decisions: list[dict]
    operator_actions: list[dict]
    rca_summary: str


class FailureArchaeology:
    """Deterministic incident reconstruction for RCA."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def capture(
        self,
        incident_key: str,
        *,
        timeline: list[dict],
        cognitive_state: dict | None = None,
        topology: dict | None = None,
        governance: list[dict] | None = None,
        operator_actions: list[dict] | None = None,
    ) -> str:
        bundle = {
            "incident_key": incident_key,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "timeline": timeline,
            "cognitive_state": cognitive_state or {},
            "topology": topology or {},
            "governance_decisions": governance or [],
            "operator_actions": operator_actions or [],
        }
        return self._repo.save_incident_bundle(incident_key, bundle)

    def reconstruct(self, bundle_id: str) -> IncidentBundle | None:
        row = self._repo.get_incident_bundle(bundle_id)
        if not row:
            return None
        bundle = row["bundle"]
        rca = self._generate_rca(bundle)
        self._repo.get_incident_bundle  # keep reference
        with self._repo._connect() as conn:
            conn.execute(
                "UPDATE ops_incident_bundles SET rca_summary = ? WHERE bundle_id = ?",
                (rca, bundle_id),
            )
            conn.commit()
        return IncidentBundle(
            bundle_id=bundle_id,
            incident_key=row["incident_key"],
            timeline=bundle.get("timeline", []),
            cognitive_state=bundle.get("cognitive_state", {}),
            topology=bundle.get("topology", {}),
            governance_decisions=bundle.get("governance_decisions", []),
            operator_actions=bundle.get("operator_actions", []),
            rca_summary=rca,
        )

    @staticmethod
    def _generate_rca(bundle: dict) -> str:
        lines = [
            f"Incident: {bundle.get('incident_key')}",
            f"Captured: {bundle.get('captured_at')}",
            f"Timeline events: {len(bundle.get('timeline', []))}",
        ]
        cog = bundle.get("cognitive_state", {})
        if cog:
            lines.append(
                f"Cognitive: stability={cog.get('epistemic_stability')} "
                f"contradictions={cog.get('open_contradictions')}"
            )
        gov = bundle.get("governance_decisions", [])
        if gov:
            lines.append(f"Governance decisions: {len(gov)}")
        return "\n".join(lines)

    def export_report(self, bundle_id: str) -> str:
        inc = self.reconstruct(bundle_id)
        if not inc:
            return f"Bundle {bundle_id} not found"
        return json.dumps(
            {
                "bundle_id": inc.bundle_id,
                "incident_key": inc.incident_key,
                "rca_summary": inc.rca_summary,
                "timeline": inc.timeline,
                "cognitive_state": inc.cognitive_state,
            },
            indent=2,
        )
