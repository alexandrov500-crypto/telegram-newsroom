from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class PublicationQualityTuner:
    """Production quality adaptation from live signals."""

    repository: Week1Repository
    _topic_counts: dict[str, int] = field(default_factory=dict)

    def observe(
        self,
        signals: dict[str, Any],
        *,
        headline: str | None = None,
        topic_key: str | None = None,
    ) -> dict[str, Any]:
        quality = float(signals.get("quality_avg", 0.8))
        engagement = float(signals.get("engagement_quality", 0.75))
        queue = int(signals.get("queue_depth", 0))

        if topic_key:
            self._topic_counts[topic_key] = self._topic_counts.get(topic_key, 0) + 1

        engagement_weight = 0.3 + engagement * 0.4
        adapted_quality = quality * (0.7 + engagement_weight * 0.3)

        repetitive = False
        if topic_key and self._topic_counts.get(topic_key, 0) > 8:
            repetitive = True

        weak_headline = False
        if headline and len(headline.strip()) < 14:
            weak_headline = True

        fatigue = min(1.0, queue / 250.0 + (1.0 - engagement) * 0.3)
        decay = False
        hist = self.repository.quality_history(limit=6)
        if len(hist) >= 4:
            recent = [float(h["quality_score"]) for h in hist[:3]]
            if recent[0] < recent[-1] - 0.08:
                decay = True

        detail = {
            "adapted_quality": round(adapted_quality, 4),
            "repetitive_topic": repetitive,
            "weak_headline": weak_headline,
            "quality_decay": decay,
            "publish_fatigue": round(fatigue, 3),
            "recommendations": self._recommendations(
                adapted_quality,
                repetitive,
                weak_headline,
                decay,
                fatigue,
            ),
        }
        self.repository.save_quality(quality=adapted_quality, fatigue=fatigue, detail=detail)
        return detail

    def _recommendations(
        self,
        q: float,
        repetitive: bool,
        weak: bool,
        decay: bool,
        fatigue: float,
    ) -> list[str]:
        recs: list[str] = []
        if q < 0.72:
            recs.append("raise_quality_floor")
        if repetitive:
            recs.append("suppress_repetitive_topic")
        if weak:
            recs.append("hold_weak_headlines")
        if decay:
            recs.append("review_cognition_prompts")
        if fatigue > 0.65:
            recs.append("reduce_publish_pacing")
        return recs

    def adaptation_html(self, signals: dict[str, Any]) -> str:
        d = self.observe(signals)
        lines = ["<b>Quality adaptation</b>"]
        lines.append(f"Adapted score: {d['adapted_quality']:.2f}")
        for r in d.get("recommendations", []):
            lines.append(f"• {r}")
        if not d.get("recommendations"):
            lines.append("• no changes recommended")
        return "\n".join(lines)

    def audience_fatigue_html(self) -> str:
        hist = self.repository.quality_history(limit=1)
        fatigue = float(hist[0]["fatigue_score"]) if hist else 0.0
        level = "low" if fatigue < 0.4 else "medium" if fatigue < 0.7 else "high"
        return f"<b>Audience fatigue</b> {fatigue:.2f} ({level})"
