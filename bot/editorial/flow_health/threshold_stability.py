from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.state import load_state


def _saturation_threshold() -> float:
    try:
        return float(os.getenv("THRESHOLD_BUDGET_SATURATION_WARN", "0.85"))
    except ValueError:
        return 0.85


def analyze_threshold_stability(*, adaptive: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Advisory watch for threshold creep and budget edge-living.
    """
    st = load_state()
    relax_hist = [float(x) for x in (st.get("relaxation_budget_history") or []) if x is not None]
    thresh_hist = [float(x) for x in (st.get("cluster_threshold_history") or []) if x is not None]

    if adaptive is None:
        try:
            from bot.editorial.flow_health.adaptive import adaptive_modulation

            adaptive = adaptive_modulation()
        except Exception:
            adaptive = {}

    cluster_t = float(adaptive.get("cluster_similarity_threshold") or 0.72)
    relax = adaptive.get("relaxation") or {}
    budget_used = float(relax.get("relaxation_budget_used") or 0)
    budget_max = float(relax.get("relaxation_budget_max") or 0.25)
    budget_saturation = budget_used / budget_max if budget_max else 0.0

    avg_threshold = cluster_t
    threshold_variance = 0.0
    if len(thresh_hist) >= 3:
        avg_threshold = sum(thresh_hist) / len(thresh_hist)
        mean = avg_threshold
        threshold_variance = sum((t - mean) ** 2 for t in thresh_hist) / len(thresh_hist)

    recovery_freq = int(st.get("recovery_activation_count") or 0)
    warning = False
    reasons: list[str] = []
    if budget_saturation >= _saturation_threshold():
        warning = True
        reasons.append("relaxation_budget_near_max")
    if len(relax_hist) >= 6:
        recent = relax_hist[-6:]
        if sum(recent) / len(recent) > budget_max * 0.75:
            warning = True
            reasons.append("sustained_high_relaxation")
    if threshold_variance > 0.0025:
        warning = True
        reasons.append("cluster_threshold_volatile")

    return {
        "average_cluster_threshold": round(avg_threshold, 3),
        "current_cluster_threshold": round(cluster_t, 3),
        "threshold_variance": round(threshold_variance, 5),
        "budget_saturation": round(budget_saturation, 3),
        "recovery_activation_count": recovery_freq,
        "threshold_stability_warning": warning,
        "warning_reasons": reasons,
    }
