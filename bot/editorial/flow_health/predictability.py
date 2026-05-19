from __future__ import annotations

from typing import Any


def compute_predictability_score(
    *,
    rhythm: dict[str, Any] | None = None,
    cadence: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
    digest: dict[str, Any] | None = None,
    threshold: dict[str, Any] | None = None,
    trends: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Single operational predictability score (0–1). Higher = calmer, more intuitive.
    Heuristic only; fail-open defaults to moderate score.
    """
    try:
        if rhythm is None:
            from bot.editorial.flow_health.rhythm import compute_rhythm_modulation

            rhythm = compute_rhythm_modulation()
        if cadence is None:
            from bot.editorial.flow_health.cadence import compute_cadence_health

            cadence = compute_cadence_health()
        if category is None:
            from bot.editorial.flow_health.category_balance import compute_category_distribution

            category = compute_category_distribution()
        if digest is None:
            from bot.editorial.flow_health.digest_discipline import compute_digest_dependency

            digest = compute_digest_dependency()
        if threshold is None:
            from bot.editorial.flow_health.threshold_stability import analyze_threshold_stability

            threshold = analyze_threshold_stability()
        if trends is None:
            from bot.editorial.flow_health.trends import compute_flow_trends

            trends = compute_flow_trends()
    except Exception:
        return {"predictability_score": 0.75, "reason": "compute_failed_open"}

    components: list[float] = []

    ch = float(cadence.get("cadence_health") or 1.0)
    if 0.45 <= ch <= 1.15:
        components.append(0.9)
    elif ch < 0.35 or ch > 1.3:
        components.append(0.45)
    else:
        components.append(0.65)

    rs = float(rhythm.get("rhythm_stability") or 0.8)
    components.append(0.5 + rs * 0.5)
    if rhythm.get("burst_detected"):
        components.append(0.55)

    if category.get("imbalanced"):
        components.append(0.5)
    else:
        components.append(0.85)

    dr = float(digest.get("digest_to_publish_ratio") or 0)
    components.append(max(0.35, 1.0 - dr * 1.2))

    if threshold.get("threshold_stability_warning"):
        components.append(0.45)
    else:
        components.append(0.88)

    if trends.get("permissive_drift_warning"):
        components.append(0.4)
    else:
        components.append(0.82)

    score = round(sum(components) / len(components), 3) if components else 0.75
    band = "high"
    if score < 0.55:
        band = "low"
    elif score < 0.72:
        band = "moderate"

    return {
        "predictability_score": score,
        "predictability_band": band,
        "factors_used": len(components),
    }
