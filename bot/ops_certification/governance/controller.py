from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from bot.ops_certification.repository import OpsCertificationRepository
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)

_SENSITIVE_DEFAULT = frozenset({"election", "active_shooter", "minors", "suicide"})


@dataclass
class GovernanceController:
    """Human-in-the-loop: freeze, quarantine, consensus, sensitive topics."""

    repository: OpsCertificationRepository
    _channel_reputation: dict[int, float] = field(default_factory=dict)

    def load(self) -> None:
        row = self.repository.get_governance_state()
        runtime_state.ingestion_paused = bool(row.get("editorial_frozen"))

    def freeze_editorial(self, *, reason: str = "operator") -> None:
        runtime_state.ingestion_paused = True
        self.repository.set_governance_state(editorial_frozen=1)
        logger.warning("event=editorial_freeze reason=%s", reason)

    def unfreeze_editorial(self) -> None:
        runtime_state.ingestion_paused = False
        self.repository.set_governance_state(editorial_frozen=0)

    def emergency_veto(self) -> None:
        runtime_state.shadow_publish_only = True
        runtime_state.ingestion_paused = True
        self.repository.set_governance_state(editorial_frozen=1, quarantine_depth=999)
        logger.critical("event=emergency_veto")

    def set_quarantine_depth(self, depth: int) -> None:
        self.repository.set_governance_state(quarantine_depth=depth)

    def enable_consensus_mode(self, enabled: bool = True) -> None:
        self.repository.set_governance_state(consensus_required=1 if enabled else 0)

    def topic_blocked(self, text: str) -> bool:
        row = self.repository.get_governance_state()
        try:
            topics = json.loads(row.get("sensitive_topics_json", "[]"))
        except json.JSONDecodeError:
            topics = list(_SENSITIVE_DEFAULT)
        if not topics:
            topics = list(_SENSITIVE_DEFAULT)
        lower = text.lower()
        return any(t in lower for t in topics)

    def update_channel_reputation(self, channel_id: int, delta: float) -> float:
        current = self._channel_reputation.get(channel_id, 1.0)
        current = max(0.0, min(1.0, current + delta))
        self._channel_reputation[channel_id] = current
        return current

    def snapshot(self) -> dict[str, Any]:
        row = self.repository.get_governance_state()
        return {
            "editorial_frozen": bool(row.get("editorial_frozen")),
            "quarantine_depth": int(row.get("quarantine_depth", 0)),
            "consensus_required": bool(row.get("consensus_required")),
            "ingestion_paused": runtime_state.ingestion_paused,
            "shadow_only": runtime_state.shadow_publish_only,
            "channels_tracked": len(self._channel_reputation),
        }

    def summary_text(self) -> str:
        s = self.snapshot()
        lines = [
            "<b>Governance</b>",
            f"Frozen: {'yes' if s['editorial_frozen'] else 'no'} · "
            f"Shadow: {'yes' if s['shadow_only'] else 'no'}",
            f"Quarantine depth: {s['quarantine_depth']}",
            f"Consensus mode: {'on' if s['consensus_required'] else 'off'}",
        ]
        return "\n".join(lines)
