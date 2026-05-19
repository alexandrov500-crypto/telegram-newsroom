from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from bot.operations.archaeology import FailureArchaeology
from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class OpsIncident:
    incident_id: str
    status: str
    title: str
    severity: str
    correlation_key: str
    replay_refs: list[str]
    suggested_action: str | None = None


class IncidentLifecycleManager:
    """Open / ack / resolve incident workflow with archaeology bundles."""

    def __init__(self, repository: OperationsRepository, archaeology: FailureArchaeology) -> None:
        self._repo = repository
        self._archaeology = archaeology

    def open_incident(
        self,
        *,
        title: str,
        severity: str,
        detail: str,
        correlation_key: str,
        replay_refs: list[str] | None = None,
        suggested_action: str | None = None,
    ) -> OpsIncident:
        incident_id = f"ops_{uuid.uuid4().hex[:10]}"
        self._repo.create_ops_incident(
            incident_id=incident_id,
            title=title,
            severity=severity,
            correlation_key=correlation_key,
            detail=detail,
            replay_refs=replay_refs or [],
            suggested_action=suggested_action,
        )
        return OpsIncident(
            incident_id=incident_id,
            status="open",
            title=title,
            severity=severity,
            correlation_key=correlation_key,
            replay_refs=replay_refs or [],
            suggested_action=suggested_action,
        )

    def acknowledge(self, incident_id: str, *, operator_id: str | None = None) -> bool:
        return self._repo.update_ops_incident_status(
            incident_id, status="acked", operator_id=operator_id,
        )

    def resolve(self, incident_id: str, *, operator_id: str | None = None, note: str = "") -> bool:
        ok = self._repo.update_ops_incident_status(
            incident_id, status="resolved", operator_id=operator_id, note=note,
        )
        if ok:
            row = self._repo.get_ops_incident(incident_id)
            if row:
                self._archaeology.capture(
                    row.get("correlation_key", incident_id),
                    timeline=[{"event": "resolved", "note": note[:200]}],
                )
        return ok

    def list_open(self, limit: int = 15) -> list[dict[str, Any]]:
        return self._repo.list_incidents(status="open", limit=limit)

    def export_bundle(self, incident_id: str) -> str | None:
        row = self._repo.get_ops_incident(incident_id)
        if not row:
            return None
        return self._archaeology.capture(
            row.get("correlation_key", incident_id),
            timeline=[{"event": "export", "incident_id": incident_id}],
        )

    def format_incident_list(self, rows: list[dict]) -> str:
        if not rows:
            return "<b>Incidents</b>\nNo open incidents."
        lines = ["<b>Incidents</b>"]
        for r in rows[:12]:
            lines.append(
                f"• <code>{r['incident_id']}</code> [{r['status']}] "
                f"{r['severity']}: {r['title'][:60]}"
            )
        lines.append("\n/incident_ack · /incident_resolve · /incident_export")
        return "\n".join(lines)
