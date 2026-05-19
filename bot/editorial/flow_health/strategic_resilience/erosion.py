from __future__ import annotations

from typing import Any


def detect_architectural_erosion(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    sustainability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Slow long-term sustainability loss — system may still be stable now."""
    gov = governance or {}
    cert = certification or {}
    frz = freeze_registry or {}
    omem = operational_memory or {}
    doc = doctrine or {}
    rel = reliability or {}
    cockpit = cockpit or {}
    sust = sustainability or {}

    signals: list[str] = []
    dims = sust.get("dimensions") or {}

    if (cert.get("change_pressure") or {}).get("change_pressure_band") != "LOW":
        signals.append("recurring_operator_intervention")

    if int((rel.get("runtime_fatigue") or {}).get("runtime_fatigue_score", 0) * 10) >= 4:
        signals.append("stewardship_fatigue_signal")

    if float(frz.get("experimental_surface_ratio") or 0) >= 0.28:
        signals.append("expanding_experimental_surface")

    if float(dims.get("cadence_sustainability") or 1) < 0.5:
        signals.append("rising_cadence_instability")

    if omem.get("recurrence_detected"):
        signals.append("drift_recurrence_accumulation")

    if doc.get("doctrine_drift_detected"):
        signals.append("governance_dependence_growth")

    if len(cockpit.get("active_warnings") or []) >= 5:
        signals.append("digest_entropy_growth")

    if int((gov.get("slimming") or {}).get("consolidation", {}).get("heuristic_density") or 0) >= 5:
        signals.append("advisory_layering_growth")

    ledger = frz.get("evolution_ledger") or {}
    if sum(1 for v in ledger.values() if v.get("stability_trend") == "VOLATILE") >= 2:
        signals.append("intervention_cycle_recurrence")

    return {
        "architectural_erosion_detected": len(signals) >= 2,
        "erosion_signals": signals[:8],
        "erosion_severity": round(min(1.0, len(signals) * 0.12), 3),
    }
