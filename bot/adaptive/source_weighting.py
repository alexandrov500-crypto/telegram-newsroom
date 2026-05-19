from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bot.learning.types import OutcomeLabel
from bot.storage.learning_repository import LearningRepository
from bot.storage.source_repository import SourceRepository

logger = logging.getLogger(__name__)

WEIGHT_MIN = 0.25
WEIGHT_MAX = 1.75
DRIFT_FACTOR = 0.03


class DynamicSourceWeighting:
    """Slow, bounded, explainable source weight adaptation."""

    def __init__(
        self,
        learning: LearningRepository,
        sources: SourceRepository,
    ) -> None:
        self._learning = learning
        self._sources = sources

    def effective_trust(self, source_name: str) -> float:
        profile = self._sources.get_profile(source_name)
        weight = self._learning.get_source_weight(source_name)
        return max(0.0, min(1.0, profile.trust_score * weight))

    def recompute_all(self, *, window_hours: int = 168) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        outcomes = self._learning.outcomes_in_window(hours=window_hours)
        by_source: dict[str, list[dict]] = {}
        for row in outcomes:
            src = row.get("source")
            if src:
                by_source.setdefault(str(src), []).append(row)

        updated = 0
        for source_name, rows in by_source.items():
            profile = self._sources.get_profile(source_name)
            current_weight = self._learning.get_source_weight(source_name)
            false_esc = sum(
                1 for r in rows if r["label"] == OutcomeLabel.FALSE_POSITIVE.value
            )
            positive = sum(1 for r in rows if r["label"] == OutcomeLabel.POSITIVE.value)
            total = max(len(rows), 1)
            false_rate = false_esc / total
            precision = positive / total

            new_weight = current_weight
            reason_parts: list[str] = []

            if false_rate > 0.2:
                new_weight *= 1.0 - DRIFT_FACTOR
                reason_parts.append("false_escalation_penalty")
            if precision > 0.5:
                new_weight *= 1.0 + DRIFT_FACTOR * 0.5
                reason_parts.append("high_precision_boost")

            new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, new_weight))
            if abs(new_weight - current_weight) > 0.005:
                self._learning.upsert_source_weight(
                    source_name=source_name,
                    dynamic_weight=new_weight,
                    base_trust=profile.trust_score,
                    false_escalation_rate=false_rate,
                    reason=",".join(reason_parts) or "stable",
                )
                updated += 1
        _ = cutoff
        return updated
