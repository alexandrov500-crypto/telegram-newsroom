from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass
class ProductionQualityLearner:
    """Learn from corrections, reactions, weak patterns."""

    repository: PostGaRepository
    _headlines: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    _rolling_quality: deque[float] = field(default_factory=lambda: deque(maxlen=48))
    quality_confidence: float = 0.85

    def learn_correction(self, *, source_key: str, story_id: int) -> None:
        self.repository.record_quality_pattern(
            source_key=source_key,
            pattern_type="operator_correction",
            score=0.3,
            detail={"story_id": story_id},
        )
        self.quality_confidence *= 0.98

    def learn_reaction(self, *, source_key: str, positive: bool) -> None:
        self.repository.record_quality_pattern(
            source_key=source_key,
            pattern_type="reaction",
            score=0.8 if positive else 0.4,
        )

    def learn_reversal(self, *, source_key: str) -> None:
        self.repository.record_quality_pattern(
            source_key=source_key,
            pattern_type="reversal",
            score=0.2,
        )
        self.quality_confidence *= 0.95

    def observe_output(self, *, headline: str, summary: str, quality_overall: float) -> None:
        self._headlines.append(headline.lower()[:80])
        self._rolling_quality.append(quality_overall)
        self.quality_confidence = sum(self._rolling_quality) / len(self._rolling_quality)

        if len(headline.split()) < 4:
            self.repository.record_quality_pattern(
                source_key=None,
                pattern_type="weak_headline",
                score=0.4,
            )
        if len(summary.split()) < 20:
            self.repository.record_quality_pattern(
                source_key=None,
                pattern_type="low_value_summary",
                score=0.45,
            )
        tokens = headline.lower().split()[:3]
        if tokens:
            key = " ".join(tokens)
            counts = Counter(self._headlines)
            if counts[key] > 5:
                self.repository.record_quality_pattern(
                    source_key=None,
                    pattern_type="repetitive_headline",
                    score=0.35,
                )

    def drift_forecast(self) -> str:
        if len(self._rolling_quality) < 5:
            return "insufficient_data"
        recent = list(self._rolling_quality)[-5:]
        older = list(self._rolling_quality)[:5]
        if not older:
            return "stable"
        if sum(recent) / len(recent) < sum(older) / len(older) - 0.1:
            return "degrading"
        if sum(recent) / len(recent) > sum(older) / len(older) + 0.05:
            return "improving"
        return "stable"

    def trends_text(self) -> str:
        forecast = self.drift_forecast()
        lines = [
            "<b>Quality trends</b>",
            f"Confidence {self.quality_confidence:.2f} · forecast {forecast}",
        ]
        weak = self.repository.source_quality_scores(limit=5)
        if weak:
            lines.append("<b>Weak sources</b>")
            for s in weak[:4]:
                lines.append(f"• {s.get('source_key', '?')}: {s.get('avg_score', 0):.2f}")
        return "\n".join(lines)

    def source_quality_text(self) -> str:
        rows = self.repository.source_quality_scores(limit=12)
        lines = ["<b>Source quality</b>"]
        for r in rows:
            lines.append(f"• {r['source_key']}: {r['avg_score']:.2f} (n={r['n']})")
        if not rows:
            lines.append("No source samples yet.")
        return "\n".join(lines)
