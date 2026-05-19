from __future__ import annotations

from typing import Any


def assess_architectural_sufficiency(
    *,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Additional complexity no longer materially improves stewardship."""
    gov = governance or {}
    frz = gov.get("freeze_registry") or {}
    doc = gov.get("doctrine") or {}
    min_g = gov.get("minimalism") or {}
    sres = gov.get("strategic_resilience") or {}
    omem = gov.get("operational_memory") or {}
    rehe = gov.get("rehearsal") or {}

    signals: list[str] = []
    points = 0

    if frz.get("ultra_quiet_digest"):
        points += 1
        signals.append("invisible_digest")
    if (frz.get("drift_exposure") or {}).get("drift_exposure_band") == "MINIMAL":
        points += 1
        signals.append("minimal_drift")
    if doc.get("doctrine_alignment_status") == "ALIGNED":
        points += 1
        signals.append("stable_doctrine")
    if int(min_g.get("quiet_infrastructure_streak_days") or 0) >= 7:
        points += 1
        signals.append("quiet_continuity")
    if float(min_g.get("operational_entropy_accumulation") or 1) < 0.3:
        points += 1
        signals.append("low_entropy")
    if sres.get("long_horizon_sustainability"):
        points += 1
        signals.append("long_horizon_sustained")
    if not omem.get("recurrence_detected"):
        points += 1
        signals.append("no_meaningful_recurrence")
    if (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY":
        points += 1
        signals.append("persistent_calmness")

    sufficient = points >= 6
    return {
        "architectural_sufficiency": sufficient,
        "sufficiency_score": round(min(1.0, points / 8.0), 3),
        "sufficiency_signals": signals[:8],
    }
