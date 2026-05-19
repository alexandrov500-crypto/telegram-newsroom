from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.schema import CONFIDENCE_DECAY_RATE, MAX_CONFIDENCE_AMPLIFICATION
from bot.epistemic.types import EpistemicGovernanceDocument, EpistemicScore


@dataclass(frozen=True)
class ConfidenceInputs:
    base_score: float
    evidence_count: int = 1
    source_count: int = 1
    contradiction_count: int = 0
    replay_stability: float = 1.0
    prior_confidence: float | None = None


class ConfidenceModel:
    """Explainable confidence with bounded amplification and decay."""

    def __init__(
        self,
        repository: EpistemicRepository,
        governance: EpistemicGovernanceDocument | None = None,
    ) -> None:
        self._repo = repository
        self._gov = governance or repository.get_active_governance()

    def score(
        self,
        subject_type: str,
        subject_id: str,
        inputs: ConfidenceInputs,
        *,
        explanation_parts: list[str] | None = None,
    ) -> EpistemicScore:
        evidence_depth = min(1.0, inputs.evidence_count / 5.0)
        diversity = min(1.0, inputs.source_count / 4.0)
        contradiction_exposure = min(1.0, inputs.contradiction_count * 0.2)

        raw_confidence = (
            inputs.base_score * 0.4
            + evidence_depth * 0.25
            + diversity * 0.2
            + inputs.replay_stability * 0.15
        )
        raw_confidence -= contradiction_exposure * 0.3

        if inputs.prior_confidence is not None:
            delta = raw_confidence - inputs.prior_confidence
            capped_delta = max(
                -MAX_CONFIDENCE_AMPLIFICATION,
                min(MAX_CONFIDENCE_AMPLIFICATION, delta),
            )
            confidence = inputs.prior_confidence + capped_delta
            confidence -= CONFIDENCE_DECAY_RATE
        else:
            confidence = raw_confidence

        cap = self._gov.anti_overconfidence_cap if self._gov else 0.95
        if evidence_depth < 0.3 and self._gov:
            cap = min(cap, self._gov.max_confidence_without_evidence)
        confidence = max(0.05, min(cap, confidence))

        uncertainty = max(
            0.05,
            min(0.95, 1.0 - confidence + contradiction_exposure * 0.3),
        )

        parts = explanation_parts or []
        parts.extend(
            [
                f"evidence_depth={evidence_depth:.2f}",
                f"source_diversity={diversity:.2f}",
                f"contradiction_exposure={contradiction_exposure:.2f}",
            ]
        )
        replay_key = hashlib.sha256(f"{subject_type}:{subject_id}".encode()).hexdigest()[:16]
        score_id = str(uuid.uuid4())[:12]

        existing = self._repo.get_score(subject_type, subject_id)
        if existing:
            score_id = existing["score_id"]
            self._repo.log_confidence_change(
                score_id,
                float(existing["confidence"]),
                confidence,
                "; ".join(parts),
            )

        epistemic = EpistemicScore(
            score_id=score_id,
            subject_type=subject_type,
            subject_id=subject_id,
            confidence=round(confidence, 4),
            uncertainty=round(uncertainty, 4),
            evidence_depth=round(evidence_depth, 4),
            contradiction_exposure=round(contradiction_exposure, 4),
            source_diversity=round(diversity, 4),
            replay_stability=round(inputs.replay_stability, 4),
            explanation="; ".join(parts),
            replay_key=replay_key,
        )
        self._repo.save_score(epistemic)
        return epistemic


class ConfidencePropagation:
    """Aggregate confidence across evaluations and consensus without inflation."""

    def __init__(self, model: ConfidenceModel) -> None:
        self._model = model

    def aggregate(
        self,
        subject_type: str,
        subject_id: str,
        child_scores: list[float],
        *,
        weights: list[float] | None = None,
    ) -> EpistemicScore:
        if not child_scores:
            return self._model.score(
                subject_type,
                subject_id,
                ConfidenceInputs(base_score=0.5, evidence_count=0),
                explanation_parts=["no child scores"],
            )
        w = weights or [1.0] * len(child_scores)
        total_w = sum(w)
        mean = sum(s * wt for s, wt in zip(child_scores, w)) / total_w
        variance = sum((s - mean) ** 2 for s in child_scores) / len(child_scores)
        contradiction_proxy = int(variance > 0.04)

        return self._model.score(
            subject_type,
            subject_id,
            ConfidenceInputs(
                base_score=mean,
                evidence_count=len(child_scores),
                contradiction_count=contradiction_proxy,
            ),
            explanation_parts=[f"aggregated {len(child_scores)} scores, var={variance:.3f}"],
        )

    def decay(self, subject_type: str, subject_id: str, *, hours_elapsed: float = 1.0) -> EpistemicScore | None:
        existing = self._repo.get_score(subject_type, subject_id)
        if not existing:
            return None
        prior = float(existing["confidence"])
        decayed = max(0.05, prior - CONFIDENCE_DECAY_RATE * hours_elapsed)
        return self._model.score(
            subject_type,
            subject_id,
            ConfidenceInputs(
                base_score=decayed,
                evidence_count=int(existing.get("evidence_depth", 0) * 5),
                prior_confidence=prior,
            ),
            explanation_parts=[f"temporal decay over {hours_elapsed:.1f}h"],
        )

    @property
    def _repo(self) -> EpistemicRepository:
        return self._model._repo
