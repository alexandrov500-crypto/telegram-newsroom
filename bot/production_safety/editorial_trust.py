from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.types import StoryTrustState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditorialTrustInput:
    publish_confidence: float | None
    source_count: int
    duplicate_narrative: bool
    misinfo_score: float
    hallucination_suspicion: float
    open_contradictions: int
    operator_approved: bool
    unsafe_content: bool


class EditorialTrustEngine:
    """Publish trust: TRUSTED / REVIEW_REQUIRED / BLOCKED."""

    def __init__(self, settings: ProductionSafetySettings) -> None:
        self._settings = settings

    def evaluate(self, inp: EditorialTrustInput) -> StoryTrustState:
        if inp.unsafe_content:
            return StoryTrustState.BLOCKED
        if inp.misinfo_score >= 0.85 and not inp.operator_approved:
            return StoryTrustState.BLOCKED
        if inp.duplicate_narrative and not inp.operator_approved:
            return StoryTrustState.BLOCKED
        if inp.hallucination_suspicion >= 0.8 and not inp.operator_approved:
            return StoryTrustState.BLOCKED
        conf = inp.publish_confidence if inp.publish_confidence is not None else 0.5
        if conf < self._settings.min_publish_confidence and not inp.operator_approved:
            return StoryTrustState.REVIEW_REQUIRED
        if inp.source_count < self._settings.min_source_diversity and not inp.operator_approved:
            return StoryTrustState.REVIEW_REQUIRED
        if inp.open_contradictions >= 3 and not inp.operator_approved:
            return StoryTrustState.REVIEW_REQUIRED
        if inp.hallucination_suspicion >= 0.5 and not inp.operator_approved:
            return StoryTrustState.REVIEW_REQUIRED
        return StoryTrustState.TRUSTED

    def evaluate_from_item(
        self,
        item: Any,
        *,
        operator_approved: bool = False,
        misinfo_score: float = 0.0,
        open_contradictions: int = 0,
        source_count: int = 1,
    ) -> StoryTrustState:
        conf = getattr(item, "priority_score", None)
        if conf is not None:
            conf = float(conf) / 100.0 if float(conf) > 1 else float(conf)
        return self.evaluate(
            EditorialTrustInput(
                publish_confidence=conf,
                source_count=source_count,
                duplicate_narrative=False,
                misinfo_score=misinfo_score,
                hallucination_suspicion=0.0,
                open_contradictions=open_contradictions,
                operator_approved=operator_approved,
                unsafe_content=False,
            ),
        )
