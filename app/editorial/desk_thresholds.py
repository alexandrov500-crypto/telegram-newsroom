"""Category-aware desk thresholds (env-driven, respects starvation floor)."""

from __future__ import annotations

import os

from app.editorial.desk_starvation import DeskThresholdContext, desk_threshold_context


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def category_min_publish_score(category: str, ctx: DeskThresholdContext | None = None) -> float:
    """
    Per-category minimum quality (before starvation global cap).
    Never below DESK_STARVATION_MIN_SCORE_FLOOR when starvation is active.
    """
    base = ctx or desk_threshold_context()
    cat = (category or "market").strip().lower()
    if cat == "breaking":
        floor = _env_float("DESK_CATEGORY_BREAKING_MIN", 48.0, lo=35.0, hi=70.0)
    elif cat == "macro":
        floor = _env_float("DESK_CATEGORY_MACRO_MIN", 38.0, lo=28.0, hi=60.0)
    elif cat == "market":
        floor = _env_float("DESK_CATEGORY_MARKET_MIN", 40.0, lo=28.0, hi=60.0)
    else:
        floor = _env_float("DESK_CATEGORY_ANALYSIS_MIN", 36.0, lo=28.0, hi=55.0)
    effective = max(floor, base.lower_priority_score + 1.0)
    if base.publish_starvation_detected:
        effective = min(effective, base.effective_min_publish_score)
    else:
        effective = min(effective, base.base_min_publish_score)
    return round(effective, 2)


def category_thresholds_snapshot(ctx: DeskThresholdContext | None = None) -> dict[str, float]:
    base = ctx or desk_threshold_context()
    return {
        "global_base": base.base_min_publish_score,
        "global_effective": base.effective_min_publish_score,
        "market": category_min_publish_score("market", base),
        "macro": category_min_publish_score("macro", base),
        "breaking": category_min_publish_score("breaking", base),
        "analysis": category_min_publish_score("analysis", base),
        "starvation_active": base.starvation_active,
    }
