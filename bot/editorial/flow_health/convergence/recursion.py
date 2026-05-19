from __future__ import annotations

from typing import Any

_LAYER_KEYS = (
    "certification",
    "freeze_registry",
    "operational_memory",
    "doctrine",
    "strategic_resilience",
    "minimalism",
    "closure",
    "legacy",
    "observability",
)


def detect_stewardship_recursion(
    *,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Meta-governance inflation — advisory only, not a bug."""
    gov = governance or {}
    signals: list[str] = []

    layers_present = sum(1 for k in _LAYER_KEYS if gov.get(k))
    if layers_present >= 8:
        signals.append("deep_maturity_layer_stack")

    _DIGEST_FIELDS = (
        "minimalism_digest_lines",
        "doctrine_digest_lines",
        "resilience_digest_lines",
        "closure_digest_lines",
        "legacy_digest_lines",
        "observability_digest_lines",
        "memory_stewardship_lines",
        "stewardship_summary_lines",
    )
    digest_sources = 0
    for key in (
        "minimalism",
        "doctrine",
        "strategic_resilience",
        "closure",
        "legacy",
        "observability",
        "operational_memory",
        "freeze_registry",
    ):
        block = gov.get(key) or {}
        if any(block.get(field) for field in _DIGEST_FIELDS):
            digest_sources += 1

    if digest_sources >= 4:
        signals.append("overlapping_stewardship_digest_sources")

    sat = (gov.get("closure") or {}).get("governance_saturation") or {}
    if sat.get("governance_saturation_band") in ("HIGH", "SATURATED") and layers_present >= 7:
        signals.append("saturation_with_full_layer_stack")

    obs = gov.get("observability") or {}
    if obs.get("governance_cohesion_status") == "FRAGMENTED" and layers_present >= 6:
        signals.append("cohesion_fragmented_amid_maturity_stack")

    min_g = gov.get("minimalism") or {}
    red = min_g.get("redundancy") or {}
    if red.get("governance_redundancy_detected") and min_g.get("invisible_digest_mode"):
        signals.append("redundancy_under_invisible_digest")

    omem = gov.get("operational_memory") or {}
    doc = gov.get("doctrine") or {}
    if omem.get("recurrence_detected") and doc.get("institutional_stewardship_mode"):
        signals.append("repeated_calmness_reinterpretation")

    if gov.get("observability") and gov.get("closure") and (gov.get("observability") or {}).get("cohesion"):
        signals.append("observability_describes_governance_layers")

    return {
        "stewardship_recursion_detected": len(signals) >= 2,
        "recursion_signals": signals[:6],
    }
