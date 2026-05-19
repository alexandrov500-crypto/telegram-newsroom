from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import CognitivePolicyDocument

logger = logging.getLogger(__name__)


@dataclass
class LearningDelta:
    kind: str
    target: str
    before: float
    after: float
    reason: str


class LearningCoordinator:
    """Closed-loop learning with bounded deltas and rollback support."""

    def __init__(self, repository: CognitiveRepository, policy: CognitivePolicyDocument) -> None:
        self._repo = repository
        self._policy = policy
        self._last_deltas: list[LearningDelta] = []
        self._max_delta = float(policy.learning.get("max_delta_per_cycle", 0.05))

    def learn_from_feedback(
        self,
        *,
        target_type: str,
        target_id: str,
        rating: float,
        source: str | None = None,
    ) -> list[LearningDelta]:
        deltas: list[LearningDelta] = []
        if rating >= 0.8 and source:
            delta = self._adjust_source_weight(source, +self._max_delta, "positive_operator_feedback")
            deltas.append(delta)
        elif rating <= 0.3 and source:
            delta = self._adjust_source_weight(source, -self._max_delta, "negative_operator_feedback")
            deltas.append(delta)
        self._last_deltas = deltas
        return deltas

    def learn_from_evaluation(self, target_id: str, score: float) -> LearningDelta | None:
        if score >= 0.75:
            return None
        delta = LearningDelta(
            kind="routing_penalty",
            target=target_id,
            before=1.0,
            after=max(0.5, 1.0 - self._max_delta),
            reason=f"low_evaluation_score={score:.2f}",
        )
        self._repo.audit_learning("routing", "penalize", delta.reason, {"target": target_id, "after": delta.after})
        self._last_deltas.append(delta)
        return delta

    def learn_from_publish_outcome(self, *, success: bool, source: str | None) -> LearningDelta | None:
        if not source:
            return None
        adj = self._max_delta if success else -self._max_delta
        return self._adjust_source_weight(source, adj, "publish_outcome")

    def _adjust_source_weight(self, source: str, delta: float, reason: str) -> LearningDelta:
        bounds = self._policy.learning.get("source_weight_bounds", [0.2, 2.0])
        lo, hi = float(bounds[0]), float(bounds[1])
        before = 1.0
        after = max(lo, min(hi, before + delta))
        self._repo.audit_learning(
            "source_weight",
            "adjust",
            reason,
            {"source": source, "before": before, "after": after},
        )
        delta_obj = LearningDelta("source_weight", source, before, after, reason)
        self._last_deltas.append(delta_obj)
        return delta_obj

    def rollback_last(self) -> int:
        count = len(self._last_deltas)
        for d in reversed(self._last_deltas):
            self._repo.audit_learning(d.kind, "rollback", f"reverted {d.target}", {"after": d.before})
        self._last_deltas.clear()
        return count
