from __future__ import annotations

import statistics
from dataclasses import dataclass

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class EpistemicStabilityReport:
    confidence_inflation_risk: bool
    contradiction_stagnation: bool
    homogenization_risk: bool
    alerts: tuple[str, ...]
    diversity_score: float


class EpistemicStabilityMonitor:
    """Longitudinal epistemic health during continuous operation."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def record_snapshot(
        self,
        *,
        confidence_mean: float,
        uncertainty_mean: float,
        open_contradictions: int,
        misinfo_pressure: float,
        diversity_score: float,
    ) -> EpistemicStabilityReport:
        report = self.analyze(
            confidence_mean=confidence_mean,
            uncertainty_mean=uncertainty_mean,
            open_contradictions=open_contradictions,
            misinfo_pressure=misinfo_pressure,
            diversity_score=diversity_score,
        )
        self._repo.record_epistemic_longitudinal(
            confidence_mean=confidence_mean,
            uncertainty_mean=uncertainty_mean,
            open_contradictions=open_contradictions,
            misinfo_pressure=misinfo_pressure,
            diversity_score=diversity_score,
            alerts=list(report.alerts),
        )
        return report

    def analyze(
        self,
        *,
        confidence_mean: float,
        uncertainty_mean: float,
        open_contradictions: int,
        misinfo_pressure: float,
        diversity_score: float,
    ) -> EpistemicStabilityReport:
        alerts: list[str] = []
        series = self._repo.epistemic_longitudinal_series(limit=48)
        confidence_inflation = False
        if len(series) >= 5:
            recent = [float(s["confidence_mean"] or 0) for s in series[-5:]]
            if recent[-1] - recent[0] > 0.15 and uncertainty_mean < 0.2:
                confidence_inflation = True
                alerts.append("confidence_inflation_detected")

        stagnation = open_contradictions > 20 and len(series) >= 3
        if stagnation:
            counts = [int(s["open_contradictions"] or 0) for s in series[-3:]]
            if max(counts) - min(counts) < 2:
                alerts.append("contradiction_stagnation")

        homogenization = diversity_score < 0.25
        if homogenization:
            alerts.append("consensus_homogenization_risk")

        if misinfo_pressure > 0.7:
            alerts.append("misinformation_pressure_elevated")

        if series:
            epistemic_vals = [float(s.get("epistemic_stability", 0) or 0) for s in series if "epistemic_stability" in s]
            if len(epistemic_vals) >= 3 and statistics.mean(epistemic_vals[-3:]) < 0.6:
                alerts.append("epistemic_stability_regression")

        return EpistemicStabilityReport(
            confidence_inflation_risk=confidence_inflation,
            contradiction_stagnation=stagnation,
            homogenization_risk=homogenization,
            alerts=tuple(alerts),
            diversity_score=diversity_score,
        )

    def timeline_for_explorer(self) -> list[dict]:
        return self._repo.epistemic_longitudinal_series(limit=100)
