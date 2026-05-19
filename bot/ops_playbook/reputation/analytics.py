from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository


@dataclass
class ChannelReputationAnalytics:
    repository: OpsPlaybookRepository
    _history: list[float] = field(default_factory=list)

    def ingest(self, signals: dict[str, Any]) -> dict[str, Any]:
        trust = float(signals.get("trust_score", 0.85))
        quality = float(signals.get("quality_avg", 0.8))
        corrections = float(signals.get("correction_rate", 0.02))
        reversals = float(signals.get("reversal_rate", 0.01))
        engagement = float(signals.get("engagement_quality", 0.75))
        source_rep = float(signals.get("source_reputation_avg", 0.8))
        ml_consistency = float(signals.get("multilingual_trust", 0.82))

        score = (
            trust * 0.25
            + quality * 0.2
            + (1.0 - corrections) * 0.15
            + (1.0 - reversals) * 0.1
            + engagement * 0.1
            + source_rep * 0.1
            + ml_consistency * 0.1
        )
        self._history.append(score)
        if len(self._history) > 48:
            self._history = self._history[-48:]

        volatility = self._volatility()
        detail = {
            "trust_trend": signals.get("trust_trend", "stable"),
            "correction_rate": corrections,
            "reversal_rate": reversals,
            "engagement_quality": engagement,
            "source_reputation_drift": signals.get("source_degradation", []),
            "publish_consistency": quality,
            "multilingual_trust": ml_consistency,
        }
        self.repository.save_reputation(
            channel_reputation=score,
            trust_volatility=volatility,
            detail=detail,
        )
        return {
            "channel_reputation": round(score, 4),
            "trust_volatility": round(volatility, 4),
            "alert": volatility > 0.12,
        }

    def _volatility(self) -> float:
        if len(self._history) < 2:
            return 0.0
        mean = sum(self._history) / len(self._history)
        var = sum((x - mean) ** 2 for x in self._history) / len(self._history)
        return var**0.5

    def reputation_html(self) -> str:
        snap = self.repository.latest_reputation()
        if not snap:
            return "<b>Channel reputation</b>\nNo snapshots yet."
        d = snap.get("detail") or {}
        alert = "⚠ elevated volatility" if snap["trust_volatility"] > 0.12 else "stable"
        return (
            f"<b>Channel reputation</b> {snap['channel_reputation']:.2f}\n"
            f"Volatility: {snap['trust_volatility']:.3f} ({alert})\n"
            f"Trust: {d.get('trust_trend', '?')} · corrections {d.get('correction_rate', 0):.1%}"
        )

    def volatility_html(self) -> str:
        snap = self.repository.latest_reputation()
        if not snap:
            return "<b>Trust volatility</b>\nInsufficient history."
        v = snap["trust_volatility"]
        level = "low" if v < 0.06 else "medium" if v < 0.12 else "high"
        return f"<b>Trust volatility</b> {v:.3f} ({level})"
