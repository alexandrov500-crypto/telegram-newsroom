from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.state import load_state
from bot.editorial.flow_health.vitality import compute_editorial_vitality


def detect_stagnation_risk(
    *,
    vitality: dict[str, Any] | None = None,
    cadence: dict[str, Any] | None = None,
    category: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Long-window editorial sterility risk — LOW / MODERATE / HIGH.
    """
    if vitality is None:
        vitality = compute_editorial_vitality()
    if cadence is None:
        try:
            from bot.editorial.flow_health.cadence import compute_cadence_health

            cadence = compute_cadence_health()
        except Exception:
            cadence = {}
    if category is None:
        from bot.editorial.flow_health.category_balance import compute_category_distribution

        category = compute_category_distribution(hours=72)
    if novelty is None:
        from bot.editorial.flow_health.novelty_pressure import compute_novelty_pressure

        novelty = compute_novelty_pressure(hours=48)

    signals: list[str] = []
    risk_points = 0

    v_score = float(vitality.get("editorial_vitality_score") or 0.5)
    if v_score < 0.45:
        risk_points += 2
        signals.append("low_editorial_vitality")
    elif v_score < 0.58:
        risk_points += 1
        signals.append("muted_vitality")

    if float(category.get("dominant_ratio") or 0) >= 0.65:
        risk_points += 1
        signals.append("compressed_category_mix")

    if float(novelty.get("novelty_pressure_score") or 0) >= 0.6:
        risk_points += 1
        signals.append("high_novelty_pressure")

    ch = float(cadence.get("cadence_health") or 1.0)
    if 0.85 <= ch <= 1.05 and v_score < 0.55:
        risk_points += 1
        signals.append("cadence_regular_but_stale")

    st = load_state()
    daily = st.get("baseline_daily") or {}
    if len(daily) >= 5:
        recent_v = [
            float((daily[k] or {}).get("diversity_proxy") or 0)
            for k in sorted(daily.keys())[-5:]
        ]
        if recent_v and max(recent_v) - min(recent_v) < 0.08 and v_score < 0.55:
            risk_points += 1
            signals.append("flat_diversity_baseline")

    try:
        warn_at = int(os.getenv("STAGNATION_RISK_MODERATE", "2"))
        high_at = int(os.getenv("STAGNATION_RISK_HIGH", "4"))
    except ValueError:
        warn_at, high_at = 2, 4

    if risk_points >= high_at:
        level = "HIGH"
    elif risk_points >= warn_at:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "stagnation_risk": level,
        "stagnation_signals": signals,
        "risk_points": risk_points,
    }
