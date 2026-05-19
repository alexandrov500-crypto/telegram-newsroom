from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.observability.propagation import _CANONICAL_LAYERS, verify_canonical_propagation


def assess_governance_cohesion(
    *,
    governance: dict[str, Any] | None = None,
    propagation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Single operational truth across layers — advisory only."""
    gov = governance or {}
    prop = propagation or verify_canonical_propagation(enriched_governance=gov)
    signals = list(prop.get("propagation_signals") or [])

    present = sum(1 for layer in _CANONICAL_LAYERS if gov.get(layer))
    if present < len(_CANONICAL_LAYERS) - 1:
        signals.append("incomplete_governance_chain")

    if not gov.get("cockpit") and gov.get("reliability"):
        signals.append("cockpit_missing_from_governance")

    if len(signals) >= 3:
        band = "FRAGMENTED"
    elif len(signals) >= 1:
        band = "PARTIAL"
    elif present >= len(_CANONICAL_LAYERS) and prop.get("propagation_coherent"):
        band = "CANONICAL"
    elif present >= 7 and prop.get("propagation_coherent"):
        band = "COHERENT"
    else:
        band = "PARTIAL"

    return {
        "governance_cohesion_status": band,
        "cohesion_signals": signals[:8],
    }
