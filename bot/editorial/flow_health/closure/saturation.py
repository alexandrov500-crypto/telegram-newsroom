from __future__ import annotations

from typing import Any


def compute_governance_saturation(
    *,
    governance: dict[str, Any] | None = None,
    sufficiency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Governance coverage exceeds practical operational need — not shutdown signal."""
    gov = governance or {}
    suff = sufficiency or {}
    min_g = gov.get("minimalism") or {}
    red = min_g.get("redundancy") or {}

    overlap = int((red.get("overlap") or {}).get("governance_overlap_count") or 0)
    redundancy_n = int(red.get("redundancy_count") or 0)
    quiet = int(min_g.get("quiet_infrastructure_streak_days") or 0)
    compression_band = (min_g.get("compression") or {}).get("architectural_compression_band", "EXPANDED")
    invisible = bool(min_g.get("invisible_digest_mode"))

    raw = (
        overlap * 0.12
        + redundancy_n * 0.08
        + min(0.25, quiet / 60.0)
        + (0.2 if invisible else 0)
        + (0.15 if compression_band == "MINIMALIST" else 0.08 if compression_band == "COMPRESSED" else 0)
        + float(suff.get("sufficiency_score") or 0) * 0.25
    )
    index = round(max(0.0, min(1.0, raw)), 3)

    band = "UNDERMODELED"
    if index >= 0.78:
        band = "SATURATED"
    elif index >= 0.58:
        band = "MATURE"
    elif index >= 0.35:
        band = "EVOLVING"

    return {
        "governance_saturation_index": index,
        "governance_saturation_band": band,
    }
