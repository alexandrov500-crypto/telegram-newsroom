from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository


@dataclass
class EvolutionSafetyLayer:
    repository: OpsEvolutionRepository

    def evaluate(self, *, signals: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
        flags: list[str] = []
        if signals.get("optimization_count", 0) > 10:
            flags.append("over_automation")
        if signals.get("operator_attention", 1.0) < 0.4:
            flags.append("operator_disengagement")
        if signals.get("trust_score", 0.85) > 0.98:
            flags.append("trust_inflation")
        if signals.get("quality_avg", 0.8) > 0.95 and signals.get("quality_drift", "") == "degrading":
            flags.append("quality_normalization_drift")
        if signals.get("silent_failures", 0) > 3:
            flags.append("silent_failure_accumulation")
        if history and history.get("governance", {}).get("trajectory") == "falling":
            flags.append("governance_erosion")

        risk = min(1.0, len(flags) * 0.18 + float(signals.get("evolution_drift", 0)))
        self.repository.save_evolution_safety(risk, flags)
        recs: list[str] = []
        if "operator_disengagement" in flags:
            recs.append("increase_operator_touchpoints")
        if "over_automation" in flags:
            recs.append("pause_optimization_proposals")
        if risk > 0.5:
            recs.append("strategic_rollback_review")
        return {"evolution_risk": risk, "flags": flags, "recommendations": recs}
