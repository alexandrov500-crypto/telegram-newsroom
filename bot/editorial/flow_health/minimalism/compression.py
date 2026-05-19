from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.minimalism.entropy import measure_operational_entropy
from bot.editorial.flow_health.minimalism.redundancy import detect_governance_redundancy


def build_compression_candidates(
    *,
    redundancy: dict[str, Any] | None = None,
    entropy: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> list[str]:
    """Advisory simplification opportunities — no auto-cleanup."""
    red = redundancy or {}
    ent = entropy or {}
    gov = governance or {}
    candidates: list[str] = []

    for sig in red.get("redundancy_signals") or []:
        if sig == "drift_covered_by_doctrine_resilience_rehearsal":
            candidates.append("Doctrine and resilience drift overlap remains high")
        elif sig == "duplicated_stewardship_digest_lines":
            candidates.append("Stewardship digest contains persistently silent sections")
        elif sig == "operational_memory_recurrence_inactive_30d":
            candidates.append("Operational memory recurrence inactive for 30d")
        elif sig == "freeze_registry_experimental_surface_unchanged":
            candidates.append("Freeze registry experimental surface unchanged for extended period")
        elif sig == "duplicated_calmness_maturity_metrics":
            candidates.append("Calmness metrics overlap across maturity layers")

    if ent.get("entropy_elevated"):
        candidates.append("Governance layering approaching interpretive entropy")

    doc = gov.get("doctrine") or {}
    if doc.get("institutional_stewardship_mode") and len(candidates) >= 2:
        candidates.append("Consider consolidating advisory layers while preserving maturity")

    return candidates[:6]


def compute_architectural_compression_score(
    *,
    governance: dict[str, Any] | None = None,
    redundancy: dict[str, Any] | None = None,
    entropy: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    quiet_streak: int = 0,
) -> dict[str, Any]:
    """How operationally concise the newsroom remains — higher is more compressed."""
    gov = governance or {}
    red = redundancy or detect_governance_redundancy(governance=gov, cockpit=cockpit)
    ent = entropy or measure_operational_entropy(governance=gov, redundancy=red, cockpit=cockpit)
    frz = gov.get("freeze_registry") or {}
    doc = gov.get("doctrine") or {}

    bloat = float(ent.get("operational_entropy_accumulation") or 0)
    bloat += min(0.3, int(red.get("redundancy_count") or 0) * 0.05)
    subsystems = sum(1 for k in ("rehearsal", "certification", "freeze_registry", "operational_memory", "doctrine", "strategic_resilience") if gov.get(k))
    if subsystems >= 6:
        bloat += 0.08

    registry = frz.get("freeze_registry") or frz
    surface = len(registry.get("registry") or {}) / 30.0
    bloat += min(0.1, surface * 0.05)

    if not frz.get("ultra_quiet_digest"):
        bloat += 0.05
    if doc.get("complexity_continuity", {}).get("complexity_bounded"):
        bloat -= 0.06
    if quiet_streak >= 14:
        bloat -= 0.08

    score = round(max(0.0, min(1.0, 1.0 - bloat)), 3)
    band = "BLOATED"
    if score >= 0.82:
        band = "MINIMALIST"
    elif score >= 0.68:
        band = "COMPRESSED"
    elif score >= 0.45:
        band = "EXPANDED"

    return {
        "architectural_compression_score": score,
        "architectural_compression_band": band,
    }
