from __future__ import annotations

from typing import Any


def detect_expansion_pressure(
    *,
    governance: dict[str, Any] | None = None,
    saturation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complexity momentum — not engineering mistake."""
    gov = governance or {}
    sat = saturation or {}
    min_g = gov.get("minimalism") or {}
    cert = gov.get("certification") or {}

    signals: list[str] = []

    if int((min_g.get("redundancy") or {}).get("redundancy_count") or 0) >= 3:
        signals.append("advisory_duplication_growth")

    red = min_g.get("redundancy") or {}
    if int((red.get("overlap") or {}).get("governance_overlap_count") or 0) >= 2:
        signals.append("maturity_layer_recursion")

    if (cert.get("change_pressure") or {}).get("change_pressure_band") != "LOW":
        signals.append("governance_churn_despite_calm")

    if float(min_g.get("operational_entropy_accumulation") or 0) >= 0.35:
        signals.append("interpretive_logic_expansion")

    if sat.get("governance_saturation_band") == "SATURATED" and signals:
        signals.append("low_informational_delta_from_additions")

    subsystems = sum(
        1
        for k in (
            "rehearsal",
            "certification",
            "freeze_registry",
            "operational_memory",
            "doctrine",
            "strategic_resilience",
            "minimalism",
        )
        if gov.get(k)
    )
    if subsystems >= 7 and len(signals) >= 1:
        signals.append("subsystem_coupling_density")

    return {
        "expansion_pressure_detected": len(signals) >= 2,
        "expansion_pressure_signals": signals[:6],
    }
