from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.types import MisinformationAlert

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PropagationSignal:
    source_count: int
    burst_rate: float
    diversity_score: float
    narrative_anomaly: float
    replay_seen: bool


class MisinformationDetector:
    """Coordinated misinformation defense with explainable alerts."""

    def __init__(self, repository: EpistemicRepository, *, node_id: str, region: str) -> None:
        self._repo = repository
        self._node_id = node_id
        self._region = region

    def analyze(self, subject_id: str, signal: PropagationSignal) -> MisinformationAlert | None:
        risk = 0.0
        reasons: list[str] = []

        if signal.source_count < 2:
            risk += 0.25
            reasons.append("low_source_diversity")
        if signal.diversity_score < 0.3:
            risk += 0.2
            reasons.append("source_monoculture")
        if signal.burst_rate > 5.0:
            risk += 0.3
            reasons.append("propagation_burst")
        if signal.narrative_anomaly > 0.5:
            risk += 0.25
            reasons.append("narrative_anomaly")
        if signal.replay_seen and signal.burst_rate > 2.0:
            risk += 0.35
            reasons.append("replayed_misinformation_pattern")

        if risk < 0.45:
            return None

        explanation = (
            f"Misinformation risk {risk:.2f}: {', '.join(reasons)} "
            f"(region={self._region}, subject={subject_id})"
        )
        alert_id = self._repo.create_alert(
            alert_type="misinformation_risk",
            severity=min(1.0, risk),
            subject_id=subject_id,
            explanation=explanation,
            region=self._region,
            payload={
                "reasons": reasons,
                "signal": {
                    "source_count": signal.source_count,
                    "burst_rate": signal.burst_rate,
                    "diversity": signal.diversity_score,
                },
            },
        )
        try:
            from bot.observability.metrics import record_epistemic_alert

            record_epistemic_alert("misinformation_risk", risk)
        except Exception:
            pass
        return MisinformationAlert(
            alert_id=alert_id,
            alert_type="misinformation_risk",
            severity=risk,
            subject_id=subject_id,
            explanation=explanation,
        )

    def correlate_campaign(self, alert_ids: list[str]) -> dict:
        if len(alert_ids) < 2:
            return {"cluster": False, "count": len(alert_ids)}
        return {
            "cluster": True,
            "count": len(alert_ids),
            "campaign_id": f"camp:{hash(tuple(sorted(alert_ids))) % 10000:04d}",
            "explanation": f"correlated {len(alert_ids)} alerts as potential campaign",
        }

    def quarantine_recommendation(self, alert: MisinformationAlert) -> str:
        if alert.severity > 0.8:
            return "cognitive_quarantine_recommended"
        if alert.severity > 0.6:
            return "operator_review_required"
        return "monitor"
