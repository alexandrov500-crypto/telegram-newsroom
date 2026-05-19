from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bot.learning.types import EditorialOutcome, FeedbackSignal, OutcomeLabel
from bot.storage.learning_repository import LearningRepository

logger = logging.getLogger(__name__)


class EditorialFeedbackLoop:
    """Learn from publish outcomes, signal validation, and admin actions."""

    def __init__(self, repository: LearningRepository) -> None:
        self._repo = repository

    def record_publish_outcome(
        self,
        *,
        pending_news_id: int,
        story_id: int | None,
        source: str | None,
        priority_score: float,
        engagement_proxy: float = 0.5,
    ) -> EditorialOutcome:
        label = OutcomeLabel.POSITIVE.value if engagement_proxy >= 0.55 else OutcomeLabel.NEUTRAL.value
        if priority_score < 0.35:
            label = OutcomeLabel.LOW_VALUE.value
        outcome = EditorialOutcome(
            outcome_type="publish",
            label=label,
            score=engagement_proxy,
            pending_news_id=pending_news_id,
            story_id=story_id,
            source=source,
            detail={"priority_score": priority_score},
        )
        self._repo.record_outcome(outcome)
        return outcome

    def record_signal_outcome(
        self,
        *,
        signal_id: int,
        story_id: int | None,
        escalated: bool,
        became_major: bool,
    ) -> EditorialOutcome:
        if became_major:
            label = OutcomeLabel.POSITIVE.value
            score = 0.9
        elif escalated and not became_major:
            label = OutcomeLabel.FALSE_POSITIVE.value
            score = 0.2
        else:
            label = OutcomeLabel.NEUTRAL.value
            score = 0.5
        outcome = EditorialOutcome(
            outcome_type="signal_validation",
            label=label,
            score=score,
            signal_id=signal_id,
            story_id=story_id,
            detail={"escalated": escalated, "became_major": became_major},
        )
        self._repo.record_outcome(outcome)
        return outcome

    def record_admin_override(self, *, pending_news_id: int, action: str) -> None:
        self._repo.record_outcome(
            EditorialOutcome(
                outcome_type="admin_override",
                label=OutcomeLabel.NEUTRAL.value,
                score=0.5,
                pending_news_id=pending_news_id,
                detail={"action": action},
            ),
        )

    def derive_feedback_signals(self, *, window_hours: int = 168) -> list[FeedbackSignal]:
        outcomes = self._repo.outcomes_in_window(hours=window_hours)
        signals: list[FeedbackSignal] = []
        false_pos = sum(1 for o in outcomes if o["label"] == OutcomeLabel.FALSE_POSITIVE.value)
        positive = sum(1 for o in outcomes if o["label"] == OutcomeLabel.POSITIVE.value)
        low_value = sum(1 for o in outcomes if o["label"] == OutcomeLabel.LOW_VALUE.value)
        total = max(len(outcomes), 1)

        if false_pos / total > 0.15:
            signals.append(
                FeedbackSignal(
                    kind="raise_escalation_threshold",
                    weight=min(0.08, false_pos / total * 0.2),
                    target="escalation_threshold",
                ),
            )
        if low_value / total > 0.25:
            signals.append(
                FeedbackSignal(
                    kind="raise_suppress_floor",
                    weight=0.05,
                    target="suppress_below",
                ),
            )
        if positive / total > 0.4:
            signals.append(
                FeedbackSignal(
                    kind="maintain_aggressive_detection",
                    weight=-0.03,
                    target="escalation_threshold",
                ),
            )
        return signals
