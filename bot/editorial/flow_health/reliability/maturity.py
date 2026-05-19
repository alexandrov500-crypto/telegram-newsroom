from __future__ import annotations

from typing import Any


def compute_operational_maturity_index(
    *,
    trust_index: dict[str, Any] | None = None,
    realism: dict[str, Any] | None = None,
    simplicity: dict[str, Any] | None = None,
    survivability: dict[str, Any] | None = None,
    fatigue: dict[str, Any] | None = None,
    telemetry_density: dict[str, Any] | None = None,
    recovery_envelope: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Can this newsroom safely run long-term? (0–1)"""
    trust = float((trust_index or {}).get("operator_trust_index") or 0.75)
    real = float((realism or {}).get("operational_realism_index") or 0.65)
    simp = float((simplicity or {}).get("operational_simplicity_index") or 0.7)
    surv = float((survivability or {}).get("survivability_score") or 0.75)
    fat = float((fatigue or {}).get("runtime_fatigue_score") or 0.2)
    dens = float((telemetry_density or {}).get("telemetry_density_score") or 0.4)
    env_ok = 1.0 if (recovery_envelope or {}).get("envelope_within_bounds") else 0.55
    deg_penalty = 0.12 if str((degradation or {}).get("mode", "NORMAL")) != "NORMAL" else 0.0

    raw = (
        trust * 0.18
        + real * 0.18
        + simp * 0.14
        + surv * 0.18
        + env_ok * 0.14
        + (1.0 - fat) * 0.1
        + (1.0 - dens) * 0.08
    )
    score = round(max(0.0, min(1.0, raw - deg_penalty)), 3)
    band = "MATURE"
    if score < 0.55:
        band = "EARLY"
    elif score < 0.72:
        band = "STABLE"

    return {
        "operational_maturity_index": score,
        "operational_maturity_band": band,
        "long_run_safe": score >= 0.68 and surv >= 0.65,
    }
