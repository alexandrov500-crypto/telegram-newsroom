from __future__ import annotations

from typing import Any


def detect_observability_drift(
    *,
    governance: dict[str, Any] | None = None,
    cohesion: dict[str, Any] | None = None,
    propagation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational reality representation divergence — not runtime failure."""
    gov = governance or {}
    cohesion = cohesion or {}
    prop = propagation or {}
    signals: list[str] = []

    frz = gov.get("freeze_registry") or {}
    rehe = gov.get("rehearsal") or {}
    cert = gov.get("certification") or {}
    min_g = gov.get("minimalism") or {}

    exp_calm = frz.get("drift_exposure", {}).get("drift_exposure_band") == "MINIMAL"
    uptime = (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY"
    if exp_calm and not uptime:
        signals.append("telemetry_calm_digest_degraded_uptime")

    if cert.get("operational_confidence", {}).get("operational_confidence_band") == "CERTIFIED":
        if cohesion.get("governance_cohesion_status") == "FRAGMENTED":
            signals.append("maturity_telemetry_cohesion_disagreement")

    if min_g.get("invisible_digest_mode") and min_g.get("operational_entropy_accumulation", 0) >= 0.4:
        signals.append("invisible_digest_high_entropy")

    if not prop.get("propagation_coherent", True):
        signals.extend((prop.get("propagation_signals") or [])[:3])

    clos = gov.get("closure") or {}
    if clos.get("architectural_sufficiency") and clos.get("expansion_pressure_detected"):
        signals.append("sufficiency_expansion_pressure_conflict")

    return {
        "observability_drift_detected": len(signals) >= 1,
        "observability_drift_signals": signals[:6],
    }
