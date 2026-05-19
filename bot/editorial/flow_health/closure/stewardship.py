from __future__ import annotations

from typing import Any


def evaluate_operational_closure_candidate(
    *,
    governance: dict[str, Any] | None = None,
    sufficiency: dict[str, Any] | None = None,
    saturation: dict[str, Any] | None = None,
    expansion: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operationally complete for current mission scope — advisory only."""
    gov = governance or {}
    suff = sufficiency or {}
    sat = saturation or {}
    exp = expansion or {}
    cont = continuity or {}
    sres = gov.get("strategic_resilience") or {}
    doc = gov.get("doctrine") or {}
    min_g = gov.get("minimalism") or {}
    omem = gov.get("operational_memory") or {}

    candidate = bool(
        sres.get("long_horizon_sustainability")
        and doc.get("stewardship_constitution_band") in ("CONSTITUTIONAL", "ALIGNED")
        and min_g.get("architectural_compression_band") == "MINIMALIST"
        and float(min_g.get("operational_entropy_accumulation") or 1) < 0.28
        and min_g.get("invisible_digest_mode")
        and suff.get("architectural_sufficiency")
        and not exp.get("expansion_pressure_detected")
        and not omem.get("recurrence_detected")
        and int(cont.get("steady_state_streak_days") or 0) >= 7
        and sat.get("governance_saturation_band") in ("MATURE", "SATURATED")
    )

    blockers = [
        b
        for b, cond in (
            ("not_long_horizon", not sres.get("long_horizon_sustainability")),
            ("doctrine_not_constitutional", doc.get("stewardship_constitution_band") not in ("CONSTITUTIONAL", "ALIGNED")),
            ("not_minimalist", min_g.get("architectural_compression_band") != "MINIMALIST"),
            ("entropy_elevated", float(min_g.get("operational_entropy_accumulation") or 1) >= 0.28),
            ("digest_not_invisible", not min_g.get("invisible_digest_mode")),
            ("insufficient", not suff.get("architectural_sufficiency")),
            ("expansion_pressure", exp.get("expansion_pressure_detected")),
            ("recurrence", omem.get("recurrence_detected")),
            ("steady_state_short", int(cont.get("steady_state_streak_days") or 0) < 7),
        )
        if cond
    ]

    return {
        "operational_closure_candidate": candidate,
        "closure_blockers": blockers[:6],
    }
