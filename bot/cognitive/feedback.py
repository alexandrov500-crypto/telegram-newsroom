from __future__ import annotations

from bot.cognitive.learning import LearningCoordinator
from bot.cognitive.repository import CognitiveRepository


class HumanInTheLoopService:
    """Operator feedback integration with correction learning loops."""

    def __init__(
        self,
        repository: CognitiveRepository,
        learning: LearningCoordinator,
    ) -> None:
        self._repo = repository
        self._learning = learning

    def approve_evaluation(self, evaluation_id: str, *, operator_id: str | None = None) -> int:
        return self._repo.record_feedback(
            feedback_type="evaluation_approve",
            target_type="evaluation",
            target_id=evaluation_id,
            operator_id=operator_id,
            rating=1.0,
        )

    def reject_evaluation(
        self,
        evaluation_id: str,
        *,
        operator_id: str | None = None,
        annotation: str | None = None,
    ) -> int:
        fid = self._repo.record_feedback(
            feedback_type="evaluation_reject",
            target_type="evaluation",
            target_id=evaluation_id,
            operator_id=operator_id,
            annotation=annotation,
            rating=0.0,
        )
        self._learning.learn_from_feedback(
            target_type="evaluation",
            target_id=evaluation_id,
            rating=0.0,
        )
        return fid

    def override_route(
        self,
        route_id: str,
        *,
        model: str,
        operator_id: str | None = None,
        reason: str,
    ) -> int:
        return self._repo.record_feedback(
            feedback_type="route_override",
            target_type="route",
            target_id=route_id,
            operator_id=operator_id,
            annotation=reason,
            payload={"model": model},
        )

    def annotate_quality_failure(
        self,
        target_type: str,
        target_id: str,
        *,
        annotation: str,
        operator_id: str | None = None,
    ) -> int:
        fid = self._repo.record_feedback(
            feedback_type="quality_failure",
            target_type=target_type,
            target_id=target_id,
            operator_id=operator_id,
            annotation=annotation,
            rating=0.2,
        )
        return fid

    def promote_source(self, source: str, *, operator_id: str | None = None) -> list:
        self._repo.record_feedback(
            feedback_type="source_promote",
            target_type="source",
            target_id=source,
            operator_id=operator_id,
            rating=1.0,
        )
        return self._learning.learn_from_feedback(
            target_type="source",
            target_id=source,
            rating=0.95,
            source=source,
        )

    def demote_source(self, source: str, *, operator_id: str | None = None) -> list:
        self._repo.record_feedback(
            feedback_type="source_demote",
            target_type="source",
            target_id=source,
            operator_id=operator_id,
            rating=0.0,
        )
        return self._learning.learn_from_feedback(
            target_type="source",
            target_id=source,
            rating=0.1,
            source=source,
        )
