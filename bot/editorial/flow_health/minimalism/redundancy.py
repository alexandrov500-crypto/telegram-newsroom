from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.minimalism.overlap import detect_governance_overlap
from bot.editorial.flow_health.state import load_state


def detect_governance_redundancy(
    *,
    governance: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Healthy but over-described — advisory redundancy only."""
    gov = governance or {}
    cockpit = cockpit or {}
    overlap = detect_governance_overlap(governance=gov)
    redundancies: list[str] = list(overlap.get("overlap_signals") or [])

    line_sources = 0
    frz = gov.get("freeze_registry") or {}
    if frz.get("stewardship_summary_lines"):
        line_sources += 1
    if (gov.get("certification") or {}).get("stewardship_summary_lines"):
        line_sources += 1
    if (gov.get("operational_memory") or {}).get("memory_stewardship_lines"):
        line_sources += 1
    if (gov.get("doctrine") or {}).get("doctrine_digest_lines"):
        line_sources += 1
    if (gov.get("strategic_resilience") or {}).get("resilience_digest_lines"):
        line_sources += 1
    if line_sources >= 4:
        redundancies.append("duplicated_stewardship_digest_lines")

    if len(cockpit.get("cockpit_bullets") or []) >= 6 and float(cockpit.get("warning_pressure") or 0) < 0.2:
        redundancies.append("low_value_cockpit_bullets_under_calm")

    st = load_state()
    mem = st.get("operational_memory") or {}
    incidents = mem.get("incidents") or []
    if incidents and not (gov.get("operational_memory") or {}).get("recurrence_detected"):
        old = [i for i in incidents if int(i.get("last_seen_days") or 0) >= 30]
        if len(old) >= 3:
            redundancies.append("operational_memory_recurrence_inactive_30d")

    if frz.get("ultra_quiet_digest") and line_sources >= 3:
        redundancies.append("persistently_silent_stewardship_sections")

    registry = frz.get("freeze_registry") or frz
    exp_ratio = float(registry.get("experimental_surface_ratio") or 0)
    ledger = frz.get("evolution_ledger") or {}
    if exp_ratio > 0 and not any(v.get("stability_trend") == "ACTIVE" for v in ledger.values()):
        redundancies.append("freeze_registry_experimental_surface_unchanged")

    return {
        "redundancy_signals": redundancies[:10],
        "redundancy_count": len(redundancies),
        "overlap": overlap,
    }
