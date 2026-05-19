from __future__ import annotations

from typing import Any


def build_memory_stewardship_lines(
    *,
    calmness: dict[str, Any] | None = None,
    recurrence: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
    ultra_quiet: bool = False,
    all_calm: bool = False,
) -> list[str]:
    """Institutional memory lines — sparse, historically relevant only."""
    lines: list[str] = []
    calm = calmness or {}
    rec = recurrence or {}

    if ultra_quiet and all_calm:
        if calm.get("institutional_calmness_band") == "INSTITUTIONAL":
            lines.append("Institutional calmness established (historical memory)")
        return lines[:2]

    if rec.get("recurrence_detected"):
        lines.extend(rec.get("recurrence_advisory_lines") or [])

    band = calm.get("institutional_calmness_band")
    if band in ("MATURE", "INSTITUTIONAL") and not rec.get("recurrence_detected"):
        lines.append(f"Institutional calmness {calm.get('institutional_calmness_index')} · {band}")

    recovery = recovery or {}
    if recovery.get("interventions_likely_hurting") and not ultra_quiet:
        lines.append("Historical pattern: interventions correlate with churn")

    return lines[:4]
