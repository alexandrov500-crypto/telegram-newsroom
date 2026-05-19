from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.state import load_state


def apply_baseline_immunity(
    baseline: dict[str, Any],
    *,
    current_vector: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Prevent chronic degraded operation from becoming normalized baseline.
    Inflates perceived deviation when baseline encodes unhealthy norms.
    """
    if os.getenv("BASELINE_IMMUNITY_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {**baseline, "immunity_active": False}

    st = load_state()
    daily = st.get("baseline_daily") or {}
    if len(daily) < 3:
        return {**baseline, "immunity_active": False}

    keys = sorted(daily.keys())[-7:]
    vitals = [float((daily[k] or {}).get("editorial_vitality_score") or 0.5) for k in keys]
    divers = [float((daily[k] or {}).get("diversity_proxy") or 0.5) for k in keys]
    digests = [float((daily[k] or {}).get("digest_dependency_ratio") or 0) for k in keys]

    avg_v = sum(vitals) / len(vitals)
    avg_d = sum(divers) / len(divers)
    avg_digest = sum(digests) / len(digests)

    immunity_signals: list[str] = []
    immunity_boost = 0.0

    try:
        v_floor = float(os.getenv("IMMUNITY_VITALITY_FLOOR", "0.52"))
        d_floor = float(os.getenv("IMMUNITY_DIVERSITY_FLOOR", "0.38"))
    except ValueError:
        v_floor, d_floor = 0.52, 0.38

    if avg_v < v_floor:
        immunity_boost += 0.08
        immunity_signals.append("chronic_low_vitality_baseline")
    if avg_d < d_floor:
        immunity_boost += 0.06
        immunity_signals.append("chronic_low_diversity_baseline")
    if avg_digest > 0.35:
        immunity_boost += 0.05
        immunity_signals.append("chronic_digest_dependence_baseline")

    adjusted_deviation = round(
        min(1.0, float(baseline.get("baseline_deviation") or 0) + immunity_boost),
        3,
    )
    drift = baseline.get("drift_detected") or immunity_boost >= 0.1

    return {
        **baseline,
        "baseline_deviation": adjusted_deviation,
        "baseline_deviation_raw": baseline.get("baseline_deviation"),
        "immunity_active": bool(immunity_signals),
        "immunity_signals": immunity_signals,
        "immunity_boost": round(immunity_boost, 3),
        "drift_detected": drift,
    }
