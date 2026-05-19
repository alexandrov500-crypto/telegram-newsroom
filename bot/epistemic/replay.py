from __future__ import annotations

import uuid
from dataclasses import dataclass

from bot.epistemic.confidence import ConfidenceInputs, ConfidenceModel
from bot.epistemic.repository import EpistemicRepository


@dataclass(frozen=True)
class EpistemicReplayResult:
    run_id: str
    stability_score: float
    divergence_score: float
    passed: bool
    explanation: str


class EpistemicReplayValidator:
    """Replay epistemic artifacts to validate cognitive stability."""

    LANE = "epistemic"

    def __init__(self, repository: EpistemicRepository, confidence: ConfidenceModel) -> None:
        self._repo = repository
        self._confidence = confidence

    def validate_consensus(
        self,
        subject_id: str,
        *,
        original_votes: list[float],
        replay_votes: list[float],
    ) -> EpistemicReplayResult:
        run_id = str(uuid.uuid4())[:12]
        if not original_votes or not replay_votes:
            return self._finish(
                run_id, "consensus", subject_id, 0.0, 1.0, False, "missing votes",
            )

        orig_mean = sum(original_votes) / len(original_votes)
        replay_mean = sum(replay_votes) / len(replay_votes)
        divergence = abs(orig_mean - replay_mean)
        stability = max(0.0, 1.0 - divergence)
        passed = divergence < 0.15

        self._confidence.score(
            "consensus_replay",
            subject_id,
            ConfidenceInputs(base_score=replay_mean, replay_stability=stability),
            explanation_parts=[f"replay divergence={divergence:.3f}"],
        )
        return self._finish(
            run_id,
            "consensus",
            subject_id,
            stability,
            divergence,
            passed,
            f"consensus replay: orig={orig_mean:.3f} replay={replay_mean:.3f}",
        )

    def validate_confidence_propagation(
        self,
        subject_type: str,
        subject_id: str,
        *,
        original_confidence: float,
        replay_confidence: float,
    ) -> EpistemicReplayResult:
        run_id = str(uuid.uuid4())[:12]
        divergence = abs(original_confidence - replay_confidence)
        stability = max(0.0, 1.0 - divergence)
        passed = divergence < 0.1
        return self._finish(
            run_id,
            subject_type,
            subject_id,
            stability,
            divergence,
            passed,
            f"confidence replay delta={divergence:.3f}",
        )

    def _finish(
        self,
        run_id: str,
        subject_type: str,
        subject_id: str,
        stability: float,
        divergence: float,
        passed: bool,
        explanation: str,
    ) -> EpistemicReplayResult:
        self._repo.save_replay_run(
            run_id,
            subject_type=subject_type,
            subject_id=subject_id,
            stability=stability,
            divergence=divergence,
            detail={"passed": passed, "explanation": explanation},
            lane=self.LANE,
        )
        try:
            from bot.observability.metrics import record_epistemic_replay

            record_epistemic_replay(passed)
        except Exception:
            pass
        return EpistemicReplayResult(
            run_id=run_id,
            stability_score=stability,
            divergence_score=divergence,
            passed=passed,
            explanation=explanation,
        )
