from __future__ import annotations

from typing import Any


def detect_doctrine_drift(
    *,
    constitution: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Philosophical deviation — not operational failure."""
    const = constitution or {}
    frz = freeze_registry or {}
    cert = certification or {}
    omem = operational_memory or {}
    slim = slimming or {}
    cockpit = cockpit or {}

    signals: list[str] = []
    drifting = [p for p in const.get("principles") or [] if p.get("status") == "DRIFTING"]
    for p in drifting:
        signals.append(f"principle_{p.get('principle')}_drifting")

    exp = float((frz.get("drift_exposure") or {}).get("drift_exposure_index") or 0)
    if exp >= 0.38:
        signals.append("operational_intervention_fragility")

    experimental = float(frz.get("experimental_surface_ratio") or 0)
    if experimental >= 0.28:
        signals.append("experimental_surface_expansion")

    if (cert.get("change_pressure") or {}).get("change_pressure_band") != "LOW":
        signals.append("recurring_intervention_dependency")

    if int((slim.get("consolidation") or {}).get("heuristic_density") or 0) >= 5:
        signals.append("governance_layering_density")

    if len(cockpit.get("active_warnings") or []) >= 6:
        signals.append("telemetry_advisory_inflation")

    if float(cockpit.get("warning_pressure") or 0) >= 0.4:
        signals.append("digest_entropy_pressure")

    if omem.get("recurrence_detected"):
        signals.append("historical_destabilization_recurrence")

    return {
        "doctrine_drift_detected": len(signals) >= 2 or len(drifting) >= 2,
        "doctrine_drift_signals": signals[:8],
        "drifting_principles": [p.get("principle") for p in drifting],
    }
