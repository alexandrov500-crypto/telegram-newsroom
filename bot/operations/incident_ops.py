from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.operations.archaeology import FailureArchaeology
from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class IncidentExport:
    bundle_id: str
    path: Path
    rca_summary: str


class IncidentArchaeologyOps:
    """One-click forensic incident bundles."""

    def __init__(self, archaeology: FailureArchaeology, repository: OperationsRepository) -> None:
        self._archaeology = archaeology
        self._repo = repository

    def export_bundle(
        self,
        incident_key: str,
        *,
        timeline: list[dict],
        cognitive_state: dict | None = None,
        topology: dict | None = None,
        contradictions: list[dict] | None = None,
        trust_state: list[dict] | None = None,
        operator_actions: list[dict] | None = None,
        export_dir: Path,
    ) -> IncidentExport:
        bundle_id = self._archaeology.capture(
            incident_key,
            timeline=timeline,
            cognitive_state={
                **(cognitive_state or {}),
                "contradictions": contradictions or [],
                "trust_state": trust_state or [],
            },
            topology=topology,
            operator_actions=operator_actions,
        )
        inc = self._archaeology.reconstruct(bundle_id)
        rca = inc.rca_summary if inc else ""
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"incident_{incident_key}_{bundle_id}.json"
        payload = {
            "bundle_id": bundle_id,
            "incident_key": incident_key,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "rca_summary": rca,
            "timeline": timeline,
            "cognitive_state": cognitive_state,
            "topology": topology,
            "contradictions": contradictions,
            "trust_state": trust_state,
            "operator_actions": operator_actions,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with self._repo._connect() as conn:
            conn.execute(
                "UPDATE ops_incident_bundles SET exported_at = ?, rca_summary = ? WHERE bundle_id = ?",
                (datetime.now(timezone.utc).isoformat(), rca, bundle_id),
            )
            conn.commit()
        return IncidentExport(bundle_id=bundle_id, path=path, rca_summary=rca)
