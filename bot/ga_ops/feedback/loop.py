from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bot.ga_ops.repository import GaOpsRepository

logger = logging.getLogger(__name__)


@dataclass
class ProductionFeedbackLoop:
    """Reactions, corrections, reversals → source reputation + confidence decay."""

    repository: GaOpsRepository
    _confidence_decay: dict[int, float] = field(default_factory=dict)

    def record_reaction(
        self,
        *,
        source_key: str,
        channel_id: int,
        positive: bool,
    ) -> None:
        impact = 0.05 if positive else -0.12
        self.repository.record_feedback(
            source_key=source_key,
            channel_id=channel_id,
            feedback_type="reaction",
            impact=impact,
        )

    def record_operator_correction(
        self,
        *,
        source_key: str,
        story_id: int,
        detail: str = "",
    ) -> None:
        self.repository.record_feedback(
            source_key=source_key,
            channel_id=None,
            feedback_type="operator_correction",
            impact=-0.2,
            detail={"story_id": story_id, "detail": detail[:200]},
        )
        self._confidence_decay[story_id] = self._confidence_decay.get(story_id, 1.0) * 0.85
        logger.info("event=feedback_correction story_id=%d", story_id)

    def record_publish_reversal(self, *, source_key: str, pending_news_id: int) -> None:
        self.repository.record_feedback(
            source_key=source_key,
            channel_id=None,
            feedback_type="publish_reversal",
            impact=-0.35,
            detail={"pending_news_id": pending_news_id},
        )

    def source_trust_adjustment(self, source_key: str, base_trust: float) -> float:
        adj = self.repository.source_reputation_adjustment(source_key)
        return max(0.1, min(1.0, base_trust + adj))

    def story_confidence(self, story_id: int, base: float) -> float:
        decay = self._confidence_decay.get(story_id, 1.0)
        return max(0.1, base * decay)

    def snapshot(self) -> dict[str, object]:
        return {"decayed_stories": len(self._confidence_decay)}
