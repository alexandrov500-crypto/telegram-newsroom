from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IncidentWorkflowEngine:
    """Timeline reconstruction, escalation, playbooks, postmortem drafts."""

    async def build_timeline(
        self,
        incident_id: str,
        *,
        reliability: Any | None = None,
        operator_console: Any | None = None,
    ) -> str:
        lines = [f"<b>Incident timeline</b> <code>{incident_id}</code>"]
        thread_id = incident_id if incident_id.startswith("inc_") else f"inc_{incident_id}"
        if operator_console is not None:
            thread = operator_console.hub.incidents.get(thread_id)
            if thread is not None:
                return thread.timeline_text()
            lines.append("No operator thread found — using synthetic timeline.")
        if reliability is not None:
            fatal = reliability.incidents.recent_fatal_count()
            lines.append(f"Recent FATAL count: {fatal}")
        lines.append("• opened — automated detection")
        lines.append("• triage — operator review recommended")
        return "\n".join(lines)

    async def review(
        self,
        incident_id: str,
        *,
        reliability: Any | None = None,
        operator_console: Any | None = None,
    ) -> str:
        timeline = await self.build_timeline(
            incident_id,
            reliability=reliability,
            operator_console=operator_console,
        )
        severity = "error"
        rollback = "Consider /rollout_rollback if publish impact confirmed."
        postmortem = self.draft_postmortem(incident_id, severity=severity)
        return f"{timeline}\n\n<b>Review</b>\n{rollback}\n\n<b>Postmortem draft</b>\n{postmortem}"

    def draft_postmortem(self, incident_id: str, *, severity: str) -> str:
        return (
            f"Incident {incident_id} ({severity}): impact TBD. "
            "Root cause: investigate replay + event bus DLQ. "
            "Action items: verify rollout stage, confirm budget, re-run /go_live_check."
        )

    def escalation_level(self, *, fatal_count: int, slo_violations: int) -> str:
        if fatal_count > 0:
            return "SEV1"
        if slo_violations >= 3:
            return "SEV2"
        return "SEV3"

    def playbook_for(self, subsystem: str) -> str:
        playbooks = {
            "telegram": "Pause publish → check FloodWait → /publish_pause",
            "openai": "Enable cost saving → reduce cognition frequency",
            "queue": "Scale workers → inspect DLQ → /queues_live",
            "replay": "RECOVERY_MODE boot → verify snapshot",
        }
        return playbooks.get(subsystem, "Generic: /system_risk → /recovery_state")
