from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass
class PostLaunchGovernance:
    """Trust trajectory, policy snapshots, reputation trends."""

    repository: PostGaRepository
    _trust_history: list[float] = field(default_factory=list)

    def record_trust(self, score: float) -> None:
        self._trust_history.append(max(0.0, min(1.0, score)))
        if len(self._trust_history) > 168:
            self._trust_history = self._trust_history[-168:]
        self.repository.save_governance(
            trust_trajectory=self._trust_history,
            policy_snapshot={"sensitive_escalation": True, "consensus_mode": False},
        )

    def trust_trend(self) -> str:
        if len(self._trust_history) < 4:
            return "stable"
        recent = sum(self._trust_history[-4:]) / 4
        older = sum(self._trust_history[:4]) / 4
        if recent > older + 0.05:
            return "rising"
        if recent < older - 0.05:
            return "falling"
        return "stable"

    def trends_text(self) -> str:
        gov = self.repository.get_governance()
        trend = self.trust_trend()
        latest = self._trust_history[-1] if self._trust_history else 0.0
        lines = [
            "<b>Governance trends</b>",
            f"Trust {latest:.2f} · trajectory {trend}",
        ]
        if gov:
            snap = gov.get("policy_snapshot", {})
            lines.append(f"Policy snapshot keys: {len(snap)}")
        return "\n".join(lines)

    def trust_evolution_text(self) -> str:
        if not self._trust_history:
            return "No trust samples yet."
        lo = min(self._trust_history)
        hi = max(self._trust_history)
        return (
            f"<b>Trust evolution</b>\n"
            f"Current {self._trust_history[-1]:.2f} · range [{lo:.2f}, {hi:.2f}]\n"
            f"Trend: {self.trust_trend()}"
        )
