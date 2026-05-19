from __future__ import annotations

from typing import Any


def compute_operational_simplicity_index(
    *,
    config_pressure: dict[str, Any],
    warning_pressure: float,
    influences: dict[str, Any],
    degradation: dict[str, Any],
    baseline: dict[str, Any],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    """
    Higher = calmer, more maintainable operation (0–1).
    """
    cfg = float(config_pressure.get("configuration_pressure_score") or 0)
    cfg_calm = max(0.0, 1.0 - cfg * 0.9)

    warn_calm = max(0.0, 1.0 - float(warning_pressure) * 0.85)

    inf_count = int(influences.get("influence_count") or 0)
    coupling_penalty = min(0.35, max(0, inf_count - 3) * 0.06)

    mode = str(degradation.get("mode") or "NORMAL")
    deg_calm = 0.9 if mode == "NORMAL" else 0.65 if mode == "SIMPLIFIED" else 0.45

    dev = float(baseline.get("baseline_deviation") or 0)
    variance_penalty = min(0.25, dev * 0.5)

    fresh = float(freshness.get("adaptive_freshness_score") or 0.7)

    raw = (
        cfg_calm * 0.2
        + warn_calm * 0.22
        + deg_calm * 0.2
        + fresh * 0.18
        + (1.0 - coupling_penalty) * 0.2
    )
    score = round(max(0.0, min(1.0, raw - variance_penalty)), 3)
    band = "HIGH"
    if score < 0.5:
        band = "LOW"
    elif score < 0.68:
        band = "MODERATE"

    return {
        "operational_simplicity_index": score,
        "simplicity_band": band,
        "heuristic_coupling_estimate": round(coupling_penalty, 3),
    }
