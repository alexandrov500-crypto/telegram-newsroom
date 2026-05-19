from __future__ import annotations

import hashlib
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import EvaluationDimension, EvaluationResult

logger = logging.getLogger(__name__)


class BaseEvaluator(ABC):
    name: str

    @abstractmethod
    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult: ...


class SummaryQualityEvaluator(BaseEvaluator):
    name = "summary_quality"

    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult:
        title = (payload.get("title") or "").strip()
        summary = (payload.get("summary") or "").strip()
        dims = [
            EvaluationDimension("clarity", min(1.0, len(summary) / 400), explanation="length heuristic"),
            EvaluationDimension("specificity", 0.7 if len(title) > 20 else 0.4, explanation="title depth"),
            EvaluationDimension("redundancy", 0.9 if title.lower() not in summary.lower() else 0.5),
        ]
        score = sum(d.score * d.weight for d in dims) / max(len(dims), 1)
        return _result(self.name, target_type, payload, dims, score, "Summary heuristics")


class PublishRelevanceEvaluator(BaseEvaluator):
    name = "publish_relevance"

    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult:
        priority = float(payload.get("priority_score") or 0.0)
        sources = int(payload.get("source_count") or 1)
        dims = [
            EvaluationDimension("priority", min(1.0, priority), explanation="editorial priority"),
            EvaluationDimension("corroboration", min(1.0, sources / 3), explanation="multi-source"),
        ]
        score = sum(d.score for d in dims) / len(dims)
        return _result(self.name, target_type, payload, dims, score, "Publish relevance")


class NoveltyEvaluator(BaseEvaluator):
    name = "novelty"

    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult:
        cluster_size = int(payload.get("cluster_size") or 1)
        novelty = max(0.2, 1.0 - (cluster_size - 1) * 0.15)
        dims = [EvaluationDimension("novelty", novelty, explanation=f"cluster_size={cluster_size}")]
        return _result(self.name, target_type, payload, dims, novelty, "Novelty from cluster density")


class SourceReliabilityEvaluator(BaseEvaluator):
    name = "source_reliability"

    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult:
        trust = float(payload.get("source_trust") or 0.5)
        dims = [EvaluationDimension("trust", min(1.0, trust), explanation="source weight")]
        return _result(self.name, target_type, payload, dims, trust, "Source reliability score")


class DigestCoherenceEvaluator(BaseEvaluator):
    name = "digest_coherence"

    def evaluate(self, target_type: str, payload: dict) -> EvaluationResult:
        items = int(payload.get("item_count") or 0)
        coherence = min(1.0, 0.5 + items * 0.05) if items else 0.3
        dims = [EvaluationDimension("coherence", coherence, explanation=f"items={items}")]
        return _result(self.name, target_type, payload, dims, coherence, "Digest item coverage")


@dataclass
class EvaluationPolicy:
    enabled: bool = True
    evaluators: tuple[str, ...] = (
        "summary_quality",
        "publish_relevance",
        "novelty",
        "source_reliability",
    )


def _result(
    name: str,
    target_type: str,
    payload: dict,
    dims: list[EvaluationDimension],
    score: float,
    explanation: str,
) -> EvaluationResult:
    target_id = str(payload.get("target_id") or payload.get("id") or "unknown")
    replay_key = hashlib.sha256(f"{name}:{target_type}:{target_id}".encode()).hexdigest()[:16]
    return EvaluationResult(
        evaluation_id=str(uuid.uuid4()),
        target_type=target_type,
        target_id=target_id,
        evaluator_name=name,
        score=round(score, 4),
        dimensions=dims,
        explanation=explanation,
        replay_key=replay_key,
    )


_BUILTIN: dict[str, BaseEvaluator] = {
    "summary_quality": SummaryQualityEvaluator(),
    "publish_relevance": PublishRelevanceEvaluator(),
    "novelty": NoveltyEvaluator(),
    "source_reliability": SourceReliabilityEvaluator(),
    "digest_coherence": DigestCoherenceEvaluator(),
}


class EvaluationPipeline:
    """Asynchronous, replayable, explainable evaluation framework."""

    def __init__(self, repository: CognitiveRepository, policy: EvaluationPolicy | None = None) -> None:
        self._repo = repository
        self._policy = policy or EvaluationPolicy()
        self._hour_count = 0

    def register_evaluator(self, evaluator: BaseEvaluator) -> None:
        _BUILTIN[evaluator.name] = evaluator

    async def evaluate(
        self,
        target_type: str,
        payload: dict,
        *,
        evaluators: list[str] | None = None,
    ) -> list[EvaluationResult]:
        if not self._policy.enabled:
            return []
        names = evaluators or list(self._policy.evaluators)
        results: list[EvaluationResult] = []
        for name in names:
            ev = _BUILTIN.get(name)
            if ev is None:
                continue
            result = ev.evaluate(target_type, payload)
            self._repo.append_evaluation_trace(result.evaluation_id, "start", {"evaluator": name})
            self._repo.save_evaluation(result)
            self._repo.append_evaluation_trace(result.evaluation_id, "complete", {"score": result.score})
            results.append(result)
            try:
                from bot.observability.metrics import record_evaluation_score

                record_evaluation_score(name, result.score)
            except Exception:
                pass
        return results

    def aggregate_score(self, target_id: str) -> float | None:
        trend = self._repo.score_trend(target_id, limit=10)
        if not trend:
            return None
        return round(sum(trend) / len(trend), 4)
