from __future__ import annotations

import os
from typing import Any

# Tunables that materially affect publish behavior (subset — advisory scan only).
_TUNABLES: dict[str, tuple[str, str | None]] = {
    "RELAXATION_BUDGET_MAX": ("0.25", "high"),
    "RHYTHM_SMOOTHING_FACTOR": ("0.15", None),
    "MIN_STORY_DISTANCE_FOR_FLOOR": ("0.35", "low"),
    "MIN_COVERAGE_SCORE": ("0.45", None),
    "LIVE_CANARY_MAX_PER_HOUR": ("3", "high"),
    "CANARY_CAP_CEILING": ("6", None),
    "CLUSTER_THRESHOLD_STARVATION_DELTA": ("0.08", None),
    "DIGEST_MAX_RATIO_24H": ("0.35", None),
    "SEMANTIC_SIMILARITY_THRESHOLD": ("0.72", "low"),
    "BASELINE_DEVIATION_WARN": ("0.22", None),
}


def _unsafe_range(key: str, value: str) -> bool:
    try:
        if key == "RELAXATION_BUDGET_MAX":
            return float(value) > 0.35
        if key == "LIVE_CANARY_MAX_PER_HOUR":
            return int(value) > 8
        if key == "MIN_STORY_DISTANCE_FOR_FLOOR":
            return float(value) < 0.25
        if key == "SEMANTIC_SIMILARITY_THRESHOLD":
            return float(value) < 0.55 or float(value) > 0.9
    except ValueError:
        return True
    return False


def analyze_configuration_pressure() -> dict[str, Any]:
    """Advisory scan of non-default / risky env tuning — no file writes."""
    non_default: list[str] = []
    unsafe: list[str] = []
    for key, (default, _edge) in _TUNABLES.items():
        raw = os.getenv(key)
        if raw is None or str(raw).strip() == "":
            continue
        if str(raw).strip() != default:
            non_default.append(key)
        if _unsafe_range(key, str(raw).strip()):
            unsafe.append(key)

    n = len(non_default)
    pressure = round(min(1.0, n / max(1, len(_TUNABLES)) * 1.2 + len(unsafe) * 0.08), 3)
    band = "low"
    if pressure >= 0.55:
        band = "high"
    elif pressure >= 0.32:
        band = "moderate"

    return {
        "configuration_pressure_score": pressure,
        "configuration_pressure_band": band,
        "non_default_count": n,
        "non_default_keys": non_default[:12],
        "unsafe_keys": unsafe,
        "tunable_count": len(_TUNABLES),
    }
