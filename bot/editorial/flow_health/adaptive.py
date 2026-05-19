from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.funnel import funnel_summary
from bot.editorial.flow_health.relaxation import effective_relaxation_scale


def _base_cluster_threshold() -> float:
    try:
        from bot.config import get_semantic_similarity_threshold

        return float(get_semantic_similarity_threshold())
    except Exception:
        try:
            return float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", "0.72"))
        except ValueError:
            return 0.72


def _overnight_hours() -> range:
    raw = os.getenv("PUBLISH_OVERNIGHT_UTC_HOURS", "0-6")
    try:
        start_s, end_s = raw.split("-", 1)
        return range(int(start_s), int(end_s) + 1)
    except ValueError:
        return range(0, 7)


def adaptive_modulation() -> dict[str, Any]:
    """
    Bounded threshold modulation — relaxation budget + hysteresis applied.
    """
    summary = funnel_summary()
    starvation = summary.get("starvation") or {}
    counters = summary.get("counters") or {}
    fetched = int(counters.get("FETCHED", 0))
    published = int(counters.get("PUBLISHED", 0))

    starving = bool(starvation.get("detected"))
    low_volume = fetched < 20 and published < 2
    burst = fetched > 80
    overnight = datetime.now(timezone.utc).hour in _overnight_hours()

    budget = effective_relaxation_scale(
        starving=starving,
        low_volume=low_volume,
        overnight=overnight,
        burst=burst,
    )
    scale = float(budget.get("effective_scale") or 0.0)

    base_cluster = _base_cluster_threshold()
    cluster_delta = 0.0
    quality_delta = 0.0
    fatigue_delta = 0.0

    cadence_health = 1.0
    cadence_band = "healthy"
    try:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cad = compute_cadence_health()
        cadence_health = float(cad.get("cadence_health") or 1.0)
        cadence_band = str(cad.get("cadence_band") or "healthy")
    except Exception:
        pass

    if starving or low_volume:
        cluster_delta += 0.08 * scale
    if cadence_band == "under_cadence" and cadence_health < 0.55:
        cluster_delta += 0.03 * scale
        quality_delta -= 0.03 * scale
    if burst:
        cluster_delta -= 0.05
    if overnight:
        cluster_delta += 0.04 * scale
        quality_delta -= 0.05 * scale
        fatigue_delta += 0.08 * scale
    if starving:
        quality_delta -= 0.08 * scale
        fatigue_delta += 0.12 * scale

    cluster = max(0.55, min(0.92, base_cluster + cluster_delta))
    quality_similarity = max(0.45, min(0.75, 0.62 + quality_delta))
    fatigue_threshold = max(0.35, min(0.70, 0.45 + fatigue_delta))

    result = {
        "cluster_similarity_threshold": round(cluster, 3),
        "quality_similarity_threshold": round(quality_similarity, 3),
        "fatigue_threshold": round(fatigue_threshold, 3),
        "starvation_active": starving,
        "low_volume_window": low_volume,
        "high_volume_burst": burst,
        "overnight": overnight,
        "cadence_health": round(cadence_health, 3),
        "cadence_band": cadence_band,
        "relaxation": budget,
    }

    try:
        from bot.editorial.flow_health.state import load_state, save_state

        st = load_state()
        hist = list(st.get("relaxation_budget_history") or [])
        hist.append(float(budget.get("relaxation_budget_used") or 0))
        thresh_hist = list(st.get("cluster_threshold_history") or [])
        thresh_hist.append(cluster)
        save_state(
            metrics={
                "relaxation_budget_history": hist[-48:],
                "cluster_threshold_history": thresh_hist[-48:],
                "last_cluster_threshold": cluster,
                "last_effective_scale": scale,
            },
        )
    except Exception:
        pass

    return result


def effective_cluster_threshold() -> float:
    try:
        return float(adaptive_modulation()["cluster_similarity_threshold"])
    except Exception:
        return _base_cluster_threshold()
