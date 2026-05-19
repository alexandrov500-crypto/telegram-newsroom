from __future__ import annotations

from typing import Any


def compute_strategic_resilience_index(
    *,
    sustainability: dict[str, Any] | None = None,
    erosion: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Long-horizon sustainability maturity — not uptime or reliability."""
    sust = sustainability or {}
    eros = erosion or {}
    omem = operational_memory or {}
    doc = doctrine or {}
    frz = freeze_registry or {}
    rel = reliability or {}
    cert = certification or {}

    agg = float(sust.get("sustainability_aggregate") or 0.6)
    calm = float(omem.get("institutional_calmness_index") or 0.5)
    stew = float(doc.get("stewardship_constitution_score") or 0.6)
    surv = float((rel.get("survivability") or {}).get("survivability_score") or 0.7)
    exp = float((frz.get("drift_exposure") or {}).get("drift_exposure_index") or 0.25)
    recovery = (omem.get("recovery_pattern") or {}).get("recovery_quality_improving")
    bounded = bool((doc.get("complexity_continuity") or {}).get("complexity_bounded"))
    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")

    raw = (
        agg * 0.22
        + calm * 0.18
        + stew * 0.15
        + surv * 0.12
        + (1 - exp) * 0.12
        + (0.08 if recovery else 0)
        + (0.06 if bounded else 0)
        + (0.07 if chg == "LOW" else 0)
    )
    raw -= float(eros.get("erosion_severity") or 0) * 0.35

    index = round(max(0.0, min(1.0, raw)), 3)
    band = "FRAGILE"
    if index >= 0.82 and not eros.get("architectural_erosion_detected"):
        band = "LONG_HORIZON"
    elif index >= 0.68:
        band = "RESILIENT"
    elif index >= 0.45:
        band = "TOLERANT"

    return {
        "strategic_resilience_index": index,
        "strategic_resilience_band": band,
    }
