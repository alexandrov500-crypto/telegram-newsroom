from __future__ import annotations

from typing import Any


def compute_observability_integrity(
    *,
    cohesion: dict[str, Any] | None = None,
    propagation: dict[str, Any] | None = None,
    drift: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational truth consistency — not uptime or metrics coverage."""
    cohesion = cohesion or {}
    prop = propagation or {}
    drift = drift or {}
    gov = governance or {}

    raw = 0.55
    status = cohesion.get("governance_cohesion_status", "PARTIAL")
    if status == "CANONICAL":
        raw += 0.25
    elif status == "COHERENT":
        raw += 0.18
    elif status == "PARTIAL":
        raw += 0.08

    if prop.get("propagation_coherent"):
        raw += 0.15

    if not drift.get("observability_drift_detected"):
        raw += 0.12

    if gov.get("minimalism", {}).get("invisible_digest_mode"):
        raw += 0.05

    if drift.get("observability_drift_detected"):
        raw -= 0.2
    if not prop.get("propagation_coherent"):
        raw -= 0.15

    index = round(max(0.0, min(1.0, raw)), 3)
    band = "FRAGILE"
    if index >= 0.82 and status in ("COHERENT", "CANONICAL"):
        band = "CANONICAL"
    elif index >= 0.65:
        band = "STABLE"
    elif index >= 0.42:
        band = "INCONSISTENT"

    return {
        "observability_integrity_index": index,
        "observability_integrity_band": band,
    }
