from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

_BASELINE_KEYS = (
    "cadence_health",
    "coverage_score",
    "predictability_score",
    "dominant_category_ratio",
    "digest_dependency_ratio",
    "cluster_threshold",
    "relaxation_budget_used",
    "diversity_proxy",
    "editorial_vitality_score",
)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _vector_from_snapshot(
    *,
    cadence: dict[str, Any],
    coverage: dict[str, Any],
    calibration: dict[str, Any],
    adaptive: dict[str, Any],
) -> dict[str, float]:
    pred = (calibration.get("predictability") or {}).get("predictability_score", 0.75)
    cat = calibration.get("category_balance") or {}
    dig = calibration.get("digest_discipline") or {}
    relax = (adaptive.get("relaxation") or {}) if adaptive else {}
    distinct = int(coverage.get("distinct_story_clusters") or 0)
    publish_n = max(1, int(coverage.get("publish_count") or 0))
    diversity_proxy = min(1.0, distinct / publish_n)
    vitality_score = 0.5
    try:
        from bot.editorial.flow_health.vitality import compute_editorial_vitality

        vitality_score = float(
            compute_editorial_vitality(cadence=cadence).get("editorial_vitality_score") or 0.5,
        )
    except Exception:
        pass
    return {
        "cadence_health": float(cadence.get("cadence_health") or 0.0),
        "editorial_vitality_score": vitality_score,
        "coverage_score": float(coverage.get("coverage_score") or 0.0),
        "predictability_score": float(pred or 0.75),
        "dominant_category_ratio": float(cat.get("dominant_ratio") or 0.0),
        "digest_dependency_ratio": float(dig.get("digest_to_publish_ratio") or 0.0),
        "cluster_threshold": float(adaptive.get("cluster_similarity_threshold") or 0.72),
        "relaxation_budget_used": float(relax.get("relaxation_budget_used") or 0.0),
        "diversity_proxy": diversity_proxy,
    }


def update_daily_baseline(
    vector: dict[str, float],
    *,
    max_days: int = 14,
) -> None:
    if os.getenv("BASELINE_GOVERNANCE_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    try:
        st = load_state()
        daily: dict[str, dict[str, float]] = dict(st.get("baseline_daily") or {})
        daily[_utc_day()] = {k: round(float(vector.get(k, 0)), 4) for k in _BASELINE_KEYS}
        keys = sorted(daily.keys())[-max_days:]
        daily = {k: daily[k] for k in keys}
        save_state(metrics={"baseline_daily": daily, "baseline_updated_at": _utc_day()})
    except Exception:
        pass


def _mean_vector(vectors: list[dict[str, float]]) -> dict[str, float]:
    if not vectors:
        return {}
    out: dict[str, float] = {}
    for key in _BASELINE_KEYS:
        vals = [float(v.get(key, 0)) for v in vectors]
        out[key] = sum(vals) / len(vals)
    return out


def compute_baseline_deviation(
    current: dict[str, float],
    *,
    window_days: int = 7,
) -> dict[str, Any]:
    """
    Long-window drift vs rolling daily baselines stored in ops_flow_health_state.
    """
    st = load_state()
    daily: dict[str, dict[str, float]] = dict(st.get("baseline_daily") or {})
    if not daily:
        return {
            "baseline_deviation": 0.0,
            "baseline_samples": 0,
            "per_metric_deviation": {},
            "drift_detected": False,
            "window_label": f"{window_days}d",
        }

    keys = sorted(daily.keys())[-window_days:]
    baseline = _mean_vector([daily[k] for k in keys])
    per: dict[str, float] = {}
    deltas: list[float] = []
    for key in _BASELINE_KEYS:
        b = float(baseline.get(key, 0))
        c = float(current.get(key, 0))
        if abs(b) < 0.02:
            d = abs(c - b)
        else:
            d = abs(c - b) / max(abs(b), 0.02)
        per[key] = round(d, 3)
        deltas.append(min(1.0, d))

    deviation = round(sum(deltas) / max(1, len(deltas)), 3)
    try:
        warn_at = float(os.getenv("BASELINE_DEVIATION_WARN", "0.22"))
    except ValueError:
        warn_at = 0.22

    return {
        "baseline_deviation": deviation,
        "baseline_samples": len(keys),
        "per_metric_deviation": per,
        "drift_detected": deviation >= warn_at,
        "window_label": f"{window_days}d",
        "baseline_means": {k: round(baseline.get(k, 0), 3) for k in _BASELINE_KEYS},
    }


def baseline_windows_summary(
    current: dict[str, float],
) -> dict[str, Any]:
    """24h / 72h / 7d deviation views from stored daily rolls."""
    st = load_state()
    daily: dict[str, dict[str, float]] = dict(st.get("baseline_daily") or {})
    keys = sorted(daily.keys())

    def _dev_for(last_n: int) -> float:
        if not keys:
            return 0.0
        subset = keys[-last_n:] if last_n <= len(keys) else keys
        base = _mean_vector([daily[k] for k in subset])
        deltas = []
        for key in _BASELINE_KEYS:
            b = float(base.get(key, 0))
            c = float(current.get(key, 0))
            deltas.append(abs(c - b) / max(abs(b), 0.02) if abs(b) >= 0.02 else abs(c - b))
        return round(sum(deltas) / max(1, len(deltas)), 3)

    return {
        "24h": _dev_for(1),
        "72h": _dev_for(3),
        "7d": _dev_for(7),
    }
