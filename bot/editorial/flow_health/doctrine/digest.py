from __future__ import annotations

from typing import Any


def build_doctrine_digest_lines(
    *,
    constitution: dict[str, Any] | None = None,
    doctrine_drift: dict[str, Any] | None = None,
    complexity: dict[str, Any] | None = None,
    stewardship_constitution: dict[str, Any] | None = None,
    institutional_mode: bool = False,
    ultra_quiet: bool = False,
) -> list[str]:
    """Infrastructure-like digest — not a philosophy report."""
    lines: list[str] = []
    const = constitution or {}
    drift = doctrine_drift or {}
    comp = complexity or {}
    stew = stewardship_constitution or {}

    if institutional_mode and ultra_quiet and not drift.get("doctrine_drift_detected"):
        lines.append("Operational doctrine remains constitutionally aligned")
        streak = int(comp.get("bounded_streak_days") or 0)
        if streak >= 7:
            lines.append(f"Complexity surface stable for {streak}d")
        return lines[:3]

    if drift.get("doctrine_drift_detected"):
        for sig in (drift.get("doctrine_drift_signals") or [])[:2]:
            if "governance_layering" in sig:
                lines.append("Governance layering increased beyond historical calm baseline")
            elif "telemetry" in sig:
                lines.append("Telemetry expansion exceeds calmness doctrine")
            elif "experimental" in sig:
                lines.append("Experimental surface expanding beyond doctrine containment")
            else:
                lines.append(f"Doctrine drift signal: {sig.replace('_', ' ')}")

    band = stew.get("stewardship_constitution_band")
    if band not in (None, "ALIGNED", "CONSTITUTIONAL") and not ultra_quiet:
        lines.append(
            f"Constitution {stew.get('stewardship_constitution_score')} · {band}",
        )

    for adv in comp.get("complexity_advisories") or []:
        if adv not in lines:
            lines.append(adv)

    if const.get("doctrine_alignment_status") == "ALIGNED" and not lines and not ultra_quiet:
        lines.append("Doctrine alignment stable")

    return lines[:5]
