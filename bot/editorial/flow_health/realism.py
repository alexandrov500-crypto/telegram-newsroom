from __future__ import annotations

from typing import Any


def compute_operational_realism_index(
    *,
    vitality: dict[str, Any],
    stagnation: dict[str, Any],
    novelty: dict[str, Any],
    responsiveness: dict[str, Any],
    longtail: dict[str, Any],
    cadence: dict[str, Any],
    coverage: dict[str, Any],
    trust_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Does the newsroom still behave like a living publication? (0–1)
    Complements operator_trust_index (stability-focused).
    """
    v = float(vitality.get("editorial_vitality_score") or 0.5)
    np = float(novelty.get("novelty_pressure_score") or 0.0)
    novelty_component = max(0.0, 1.0 - np * 0.85)

    ch = float(cadence.get("cadence_health") or 1.0)
    cadence_realism = 0.8 if 0.4 <= ch <= 1.15 else 0.5

    cov = float(coverage.get("coverage_score") or 0.5)
    diversity = min(1.0, cov * 0.7 + float(coverage.get("distinct_story_clusters") or 0) / 6 * 0.3)

    longtail_c = min(1.0, float(longtail.get("longtail_share") or 0) * 4.0 + 0.35)

    resp_c = 0.75
    if responsiveness.get("medium_cycle_active"):
        resp_c = 0.88

    stag = stagnation.get("stagnation_risk", "LOW")
    stagnation_penalty = {"LOW": 0.0, "MODERATE": 0.12, "HIGH": 0.28}.get(str(stag), 0.0)

    trust_penalty = 0.0
    if trust_index and trust_index.get("metric_illusion_risk"):
        trust_penalty = 0.1

    raw = (
        v * 0.28
        + novelty_component * 0.18
        + cadence_realism * 0.14
        + diversity * 0.14
        + longtail_c * 0.12
        + resp_c * 0.14
    )
    score = round(max(0.0, min(1.0, raw - stagnation_penalty - trust_penalty)), 3)

    band = "HIGH"
    if score < 0.55:
        band = "LOW"
    elif score < 0.72:
        band = "MODERATE"

    return {
        "operational_realism_index": score,
        "operational_realism_band": band,
        "living_newsroom": score >= 0.62 and str(stag) != "HIGH",
        "components": {
            "vitality": round(v, 3),
            "novelty_freshness": round(novelty_component, 3),
            "stagnation_risk": stag,
        },
    }
