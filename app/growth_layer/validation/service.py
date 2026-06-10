"""Load validation rows and assemble full analytics bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.validation.calibration import ViralityCalibrationReport, build_virality_calibration
from app.growth_layer.validation.decision import FormatDecisionVerdict, evaluate_format_decision
from app.growth_layer.validation.rankings import GrowthRankings, build_growth_rankings
from app.growth_layer.statistics.decision_metrics import evaluate_decision_reliability
from db.growth_validation_repository import list_post_growth_validation


@dataclass(frozen=True)
class GrowthValidationBundle:
    rows_30: list[dict[str, Any]]
    rows_100: list[dict[str, Any]]
    calibration_30: ViralityCalibrationReport
    calibration_100: ViralityCalibrationReport
    rankings: GrowthRankings
    decision: FormatDecisionVerdict
    reliability: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibration_30": self.calibration_30.to_dict(),
            "calibration_100": self.calibration_100.to_dict(),
            "rankings": self.rankings.to_dict(),
            "decision": self.decision.to_dict(),
            "reliability": self.reliability.to_dict() if hasattr(self.reliability, "to_dict") else self.reliability,
        }


async def load_growth_validation_bundle(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> GrowthValidationBundle:
    rows_100 = await list_post_growth_validation(session, limit=limit, final_only=True)
    rows_30 = rows_100[:30]
    reliability = evaluate_decision_reliability(rows_100)
    return GrowthValidationBundle(
        rows_30=rows_30,
        rows_100=rows_100,
        calibration_30=build_virality_calibration(rows_30),
        calibration_100=build_virality_calibration(rows_100),
        rankings=build_growth_rankings(rows_100),
        decision=evaluate_format_decision(rows_100),
        reliability=reliability,
    )
