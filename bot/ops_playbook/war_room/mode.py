from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository

logger = logging.getLogger(__name__)


@dataclass
class WarRoomMode:
    """Incident war room — timeline, checklist, rollback recommendations."""

    repository: OpsPlaybookRepository
    _alert_freeze: bool = field(default=False, init=False)

    @property
    def alert_freeze_active(self) -> bool:
        return self._alert_freeze

    def start(self, incident_id: str, signals: dict[str, Any]) -> str:
        rec = self._rollback_recommendation(signals)
        self.repository.start_war_room(incident_id, snapshot=signals)
        self.repository.update_war_room(
            incident_id,
            rollback_recommendation=rec,
        )
        self._alert_freeze = True
        logger.warning("event=war_room_started incident=%s", incident_id)
        return (
            f"<b>War room started</b> <code>{incident_id}</code>\n"
            "Nonessential alerts frozen · elevated logging\n"
            f"Rollback hint: {rec}"
        )

    def status(self, incident_id: str | None = None) -> str:
        if incident_id:
            row = self.repository.get_war_room(incident_id)
        else:
            active = self.repository.active_war_room()
            row = self.repository.get_war_room(active["incident_id"]) if active else None
        if not row:
            return "No active war room."
        iid = row["incident_id"]
        checklist = row.get("checklist") or {}
        done = sum(1 for v in checklist.values() if v)
        total = max(len(checklist), 1)
        lines = [
            f"<b>War room</b> <code>{iid}</code>",
            f"Started: {row.get('started_at', '?')}",
            f"Checklist: {done}/{total}",
            f"Rollback: {row.get('rollback_recommendation') or 'pending'}",
        ]
        timeline = row.get("timeline") or []
        for ev in timeline[-4:]:
            lines.append(f"• {ev.get('t', '?')}: {ev.get('event', '?')}")
        notes = row.get("notes") or []
        if notes:
            lines.append(f"Notes: {len(notes)}")
        return "\n".join(lines)

    def add_note(self, incident_id: str, operator_id: str, text: str) -> None:
        row = self.repository.get_war_room(incident_id)
        if not row:
            return
        notes = list(row.get("notes") or [])
        notes.append({"operator": operator_id, "text": text[:500]})
        timeline = list(row.get("timeline") or [])
        from datetime import datetime, timezone

        timeline.append(
            {"t": datetime.now(timezone.utc).isoformat(), "event": f"note:{operator_id}"},
        )
        self.repository.update_war_room(incident_id, timeline=timeline, notes=notes)

    def stop(self, incident_id: str) -> str:
        self.repository.stop_war_room(incident_id)
        self._alert_freeze = False
        logger.info("event=war_room_stopped incident=%s", incident_id)
        return f"War room <code>{incident_id}</code> closed."

    def _rollback_recommendation(self, signals: dict[str, Any]) -> str:
        if float(signals.get("publish_failure_rate", 0)) > 0.05:
            return "/rollout_rollback + SHADOW_PUBLISH_ONLY=true"
        if float(signals.get("scaling_risk", 0)) > 0.7:
            return "Throttle ingest · /campaign_mode_stop if active"
        if signals.get("open_incidents", 0) > 2:
            return "INTERNAL_SHADOW · pause auto-approval"
        return "Monitor 15m · /go_live_check"
