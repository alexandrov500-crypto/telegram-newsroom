"""Predicted virality vs measured post performance."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.growth_layer.virality.tiers import classify_virality_tier
from app.growth_layer.validation.status import filter_final_rows


_TIER_LABEL = {
    "standard": "low",
    "enhanced": "medium",
    "viral_candidate": "high",
    "unknown": "low",
}


@dataclass(frozen=True)
class ViralityCalibrationReport:
    sample_size: int
    correlation: float | None
    mae: float | None
    tier_distribution: dict[str, int] = field(default_factory=dict)
    tier_avg_engagement: dict[str, float] = field(default_factory=dict)
    tier_avg_forward_rate: dict[str, float] = field(default_factory=dict)
    tier_confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    rows: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "correlation": self.correlation,
            "mae": self.mae,
            "tier_distribution": dict(self.tier_distribution),
            "tier_avg_engagement": dict(self.tier_avg_engagement),
            "tier_avg_forward_rate": dict(self.tier_avg_forward_rate),
            "tier_confusion_matrix": {k: dict(v) for k, v in self.tier_confusion_matrix.items()},
        }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x <= 1e-9 or den_y <= 1e-9:
        return None
    return round(num / (den_x * den_y), 4)


def _mae(predicted: list[float], actual: list[float]) -> float | None:
    if len(predicted) < 1 or len(predicted) != len(actual):
        return None
    return round(sum(abs(p - a) for p, a in zip(predicted, actual)) / len(predicted), 4)


def predicted_tier_label(row: dict[str, Any]) -> str:
    tier = str(row.get("virality_tier") or "").strip()
    if tier:
        return _TIER_LABEL.get(tier, "low")
    score = int(row.get("predicted_virality") or 0)
    return _TIER_LABEL.get(classify_virality_tier(score).value, "low")


def actual_tier_label(row: dict[str, Any]) -> str:
    if row.get("actual_virality_tier"):
        return _TIER_LABEL.get(str(row["actual_virality_tier"]), "low")
    vir = row.get("actual_virality_score")
    if vir is not None:
        score = int(round(float(vir) * 100))
        return _TIER_LABEL.get(classify_virality_tier(score).value, "low")
    eng = row.get("actual_engagement")
    if eng is not None:
        score = int(round(float(eng) * 100))
        return _TIER_LABEL.get(classify_virality_tier(score).value, "low")
    return "low"


def build_tier_confusion_matrix(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {
        "high": {"high": 0, "medium": 0, "low": 0},
        "medium": {"high": 0, "medium": 0, "low": 0},
        "low": {"high": 0, "medium": 0, "low": 0},
    }
    for r in rows:
        pred = predicted_tier_label(r)
        actual = actual_tier_label(r)
        if pred not in matrix:
            matrix[pred] = {"high": 0, "medium": 0, "low": 0}
        matrix[pred][actual] = matrix[pred].get(actual, 0) + 1
    return matrix


def build_virality_calibration(rows: list[dict[str, Any]], *, final_only: bool = True) -> ViralityCalibrationReport:
    """
    Compare predicted virality (0–100) with actual engagement (0–1) and forward rate.
    Uses FINAL observations only by default.
    """
    usable = filter_final_rows(rows) if final_only else [r for r in rows if r.get("actual_engagement") is not None]
    predicted_norm = [float(r.get("predicted_virality") or 0) / 100.0 for r in usable]
    actual_eng = [float(r["actual_engagement"]) for r in usable]
    corr = _pearson(predicted_norm, actual_eng)
    mae = _mae(predicted_norm, actual_eng)

    tiers: dict[str, int] = {}
    tier_eng: dict[str, list[float]] = {}
    tier_fr: dict[str, list[float]] = {}
    for r in usable:
        tier = str(r.get("virality_tier") or "unknown")
        tiers[tier] = tiers.get(tier, 0) + 1
        tier_eng.setdefault(tier, []).append(float(r["actual_engagement"]))
        if r.get("actual_forward_rate") is not None:
            tier_fr.setdefault(tier, []).append(float(r["actual_forward_rate"]))

    return ViralityCalibrationReport(
        sample_size=len(usable),
        correlation=corr,
        mae=mae,
        tier_distribution=tiers,
        tier_avg_engagement={k: round(sum(v) / len(v), 4) for k, v in tier_eng.items()},
        tier_avg_forward_rate={k: round(sum(v) / len(v), 4) for k, v in tier_fr.items()},
        tier_confusion_matrix=build_tier_confusion_matrix(usable),
        rows=tuple(usable[:20]),
    )
