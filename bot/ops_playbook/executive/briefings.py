from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutiveIncidentBriefing:
    """Mobile-optimized executive incident briefs."""

    def build(self, incident_id: str, context: dict[str, Any]) -> str:
        confidence = float(context.get("confidence", 0.7))
        return (
            f"<b>Executive brief</b> <code>{incident_id[:16]}</code>\n\n"
            f"<b>What</b>\n{context.get('summary', 'Incident under investigation')}\n\n"
            f"<b>Impact</b>\n{context.get('impact', 'Limited — monitoring')}\n\n"
            f"<b>Mitigation</b>\n{context.get('mitigation', 'Standard runbook engaged')}\n\n"
            f"<b>Status</b>\n{context.get('status', 'Active')}\n\n"
            f"<b>Risk outlook</b>\n{context.get('risk_outlook', 'Contained')}\n\n"
            f"<b>Rollback</b>\n{context.get('rollback_status', 'Ready')}\n\n"
            f"<b>Operator actions</b>\n{context.get('operator_actions', 'War room optional')}\n\n"
            f"<b>Confidence</b> {confidence:.0%}"
        )

    def from_signals(self, incident_id: str, signals: dict[str, Any]) -> str:
        ctx = {
            "summary": signals.get(
                "incident_summary",
                f"Operational incident {incident_id}",
            ),
            "impact": signals.get(
                "incident_impact",
                f"Queue depth {signals.get('queue_depth', 0)}",
            ),
            "mitigation": signals.get(
                "mitigation",
                signals.get("rollback_recommendation", "Monitor"),
            ),
            "status": "War room active" if signals.get("war_room_active") else "Monitoring",
            "risk_outlook": f"Forecast {signals.get('risk_forecast', 0):.2f}",
            "rollback_status": (
                "Shadow ready" if signals.get("rollback_ready") else "Verify rollback"
            ),
            "operator_actions": signals.get("last_operator_action", "/go_live_check"),
            "confidence": signals.get("go_live_confidence", 0.75),
        }
        return self.build(incident_id, ctx)
