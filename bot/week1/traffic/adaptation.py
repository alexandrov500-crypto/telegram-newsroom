from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveTrafficAdapter:
    """Adaptive pacing from real engagement and Telegram pressure."""

    def score(self, signals: dict[str, Any]) -> dict[str, float]:
        engagement = float(signals.get("engagement_quality", 0.75))
        queue = int(signals.get("queue_depth", 0))
        trust = float(signals.get("trust_score", 0.85))
        tg_pressure = float(signals.get("telegram_pressure", 0.0))
        campaign = bool(signals.get("campaign_active"))

        pacing = 0.65 + engagement * 0.25 - min(queue / 400.0, 0.25)
        if campaign:
            pacing *= 0.85
        if tg_pressure > 0.5:
            pacing *= 0.7

        expansion = trust * 0.6 + engagement * 0.3 - tg_pressure * 0.4
        expansion = max(0.0, min(1.0, expansion))

        confidence = 0.5 + engagement * 0.3 + (1.0 - tg_pressure) * 0.2
        return {
            "traffic_adaptation": round(pacing, 4),
            "pacing_confidence": round(confidence, 4),
            "expansion_safety": round(expansion, 4),
        }

    def status_html(self, signals: dict[str, Any]) -> str:
        s = self.score(signals)
        return (
            "<b>Traffic adaptation</b>\n"
            f"Pacing: {s['traffic_adaptation']:.2f}\n"
            f"Confidence: {s['pacing_confidence']:.2f}\n"
            f"Expansion safety: {s['expansion_safety']:.2f}"
        )
