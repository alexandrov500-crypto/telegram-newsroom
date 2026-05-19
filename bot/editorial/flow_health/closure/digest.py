from __future__ import annotations

from typing import Any


def build_closure_digest_lines(
    *,
    closure: dict[str, Any] | None = None,
    sufficiency: dict[str, Any] | None = None,
    expansion: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    steady_state: bool = False,
) -> list[str]:
    """Almost silent at steady-state — max 1 line normally."""
    close = closure or {}
    suff = sufficiency or {}
    exp = expansion or {}
    cont = continuity or {}

    if close.get("operational_closure_candidate") and steady_state:
        return ["Operational stewardship remains in steady-state continuity"]

    if suff.get("architectural_sufficiency") and not exp.get("expansion_pressure_detected"):
        streak = int(cont.get("steady_state_streak_days") or 0)
        if streak >= 14:
            return ["Governance surface remains operationally sufficient"]
        return []

    if exp.get("expansion_pressure_detected"):
        sig = (exp.get("expansion_pressure_signals") or ["expansion pressure"])[0]
        return [f"Expansion pressure: {sig.replace('_', ' ')}"]

    return []
