from __future__ import annotations

from typing import Any


def compute_operator_trust_index(
    *,
    predictability: dict[str, Any],
    baseline: dict[str, Any],
    config_pressure: dict[str, Any],
    warning_pressure: float,
    digest_clarity: float,
    cadence: dict[str, Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    """
    Higher-level operator confidence (0–1) — complements predictability score.
    """
    pred = float(predictability.get("predictability_score") or 0.75)
    deviation = float(baseline.get("baseline_deviation") or 0.0)
    drift_penalty = min(0.35, deviation * 0.9)

    cfg_p = float(config_pressure.get("configuration_pressure_score") or 0.0)
    cfg_penalty = min(0.2, cfg_p * 0.35)

    warn_penalty = min(0.25, warning_pressure * 0.4)

    ch = float(cadence.get("cadence_health") or 1.0)
    cadence_realism = 0.85 if 0.45 <= ch <= 1.2 else 0.55

    cov = float(coverage.get("coverage_score") or 0.5)
    diversity_consistency = min(1.0, cov * 0.7 + float(coverage.get("distinct_story_clusters") or 0) / 6 * 0.3)

    raw = (
        pred * 0.28
        + cadence_realism * 0.18
        + diversity_consistency * 0.15
        + digest_clarity * 0.12
        + (1.0 - drift_penalty) * 0.15
        + (1.0 - cfg_penalty) * 0.07
        + (1.0 - warn_penalty) * 0.05
    )
    score = round(max(0.0, min(1.0, raw)), 3)
    band = "HIGH"
    if score < 0.62:
        band = "LOW"
    elif score < 0.78:
        band = "MODERATE"

    metric_illusion_risk = pred >= 0.78 and (
        deviation >= 0.2 or diversity_consistency < 0.45
    )

    return {
        "operator_trust_index": score,
        "operator_trust_band": band,
        "metric_illusion_risk": metric_illusion_risk,
        "components": {
            "predictability": round(pred, 3),
            "baseline_deviation": round(deviation, 3),
            "config_pressure": round(cfg_p, 3),
            "warning_pressure": round(warning_pressure, 3),
        },
    }
