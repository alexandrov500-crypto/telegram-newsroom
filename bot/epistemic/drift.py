from __future__ import annotations

import math
from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository


@dataclass(frozen=True)
class DriftReport:
    drift_kind: str
    entropy_score: float
    diversity_score: float
    alert: bool
    explanation: str
    recommendations: tuple[str, ...]


class DriftAnalyzer:
    """Long-term cognitive drift and anti-monoculture safeguards."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    @staticmethod
    def entropy(values: list[float]) -> float:
        if not values:
            return 0.0
        total = sum(values)
        if total <= 0:
            return 0.0
        probs = [v / total for v in values if v > 0]
        return -sum(p * math.log(p + 1e-12) for p in probs)

    def analyze_consensus_homogenization(
        self,
        recent_scores: list[float],
        *,
        region: str | None = None,
    ) -> DriftReport:
        entropy = self.entropy(recent_scores) if recent_scores else 0.0
        diversity = min(1.0, entropy / math.log(max(len(recent_scores), 2) + 1))
        alert = diversity < 0.25 and len(recent_scores) > 5
        recs: list[str] = []
        if alert:
            recs.append("inject_diverse_evaluators")
            recs.append("preserve_minority_votes")
        self._repo.record_drift_sample(
            "consensus_homogenization",
            entropy=entropy,
            diversity=diversity,
            region=region,
            detail={"scores": recent_scores[:20]},
        )
        return DriftReport(
            drift_kind="consensus_homogenization",
            entropy_score=round(entropy, 4),
            diversity_score=round(diversity, 4),
            alert=alert,
            explanation=f"entropy={entropy:.3f} diversity={diversity:.3f}",
            recommendations=tuple(recs),
        )

    def analyze_source_monoculture(
        self,
        source_distribution: dict[str, int],
        *,
        region: str | None = None,
    ) -> DriftReport:
        counts = list(source_distribution.values())
        entropy = self.entropy([float(c) for c in counts])
        max_share = max(counts) / sum(counts) if counts else 0
        diversity = 1.0 - max_share
        alert = max_share > 0.7
        recs = ["promote_source_diversity"] if alert else []
        self._repo.record_drift_sample(
            "source_monoculture",
            entropy=entropy,
            diversity=diversity,
            region=region,
        )
        return DriftReport(
            drift_kind="source_monoculture",
            entropy_score=round(entropy, 4),
            diversity_score=round(diversity, 4),
            alert=alert,
            explanation=f"top_source_share={max_share:.2f}",
            recommendations=tuple(recs),
        )

    def analyze_overconfident_routing(
        self,
        route_confidences: list[float],
        *,
        region: str | None = None,
    ) -> DriftReport:
        if not route_confidences:
            return DriftReport("overconfident_routing", 0, 1, False, "no routes", ())
        mean_conf = sum(route_confidences) / len(route_confidences)
        alert = mean_conf > 0.9
        self._repo.record_drift_sample(
            "overconfident_routing",
            entropy=mean_conf,
            diversity=1.0 - mean_conf,
            region=region,
        )
        return DriftReport(
            drift_kind="overconfident_routing",
            entropy_score=round(mean_conf, 4),
            diversity_score=round(1.0 - mean_conf, 4),
            alert=alert,
            explanation=f"mean_route_confidence={mean_conf:.3f}",
            recommendations=("reduce_routing_confidence_cap",) if alert else (),
        )
