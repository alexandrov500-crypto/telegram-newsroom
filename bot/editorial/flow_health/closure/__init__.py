from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.closure.continuity import (
    is_steady_state_day,
    touch_steady_state_continuity,
)
from bot.editorial.flow_health.closure.digest import build_closure_digest_lines
from bot.editorial.flow_health.closure.expansion import detect_expansion_pressure
from bot.editorial.flow_health.closure.saturation import compute_governance_saturation
from bot.editorial.flow_health.closure.stewardship import evaluate_operational_closure_candidate
from bot.editorial.flow_health.closure.sufficiency import assess_architectural_sufficiency


def closure_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Steady-state preservation & operational closure — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}

    sufficiency = assess_architectural_sufficiency(governance=gov)
    saturation = compute_governance_saturation(governance=gov, sufficiency=sufficiency)
    expansion = detect_expansion_pressure(governance=gov, saturation=saturation)
    steady_today = is_steady_state_day(
        governance=gov,
        sufficiency=sufficiency,
        expansion=expansion,
    )
    continuity = touch_steady_state_continuity(steady_today=steady_today)
    closure = evaluate_operational_closure_candidate(
        governance=gov,
        sufficiency=sufficiency,
        saturation=saturation,
        expansion=expansion,
        continuity=continuity,
    )
    digest_lines = build_closure_digest_lines(
        closure=closure,
        sufficiency=sufficiency,
        expansion=expansion,
        continuity=continuity,
        steady_state=steady_today,
    )

    return {
        "architectural_sufficiency": sufficiency.get("architectural_sufficiency"),
        "sufficiency": sufficiency,
        "governance_saturation": saturation,
        "governance_saturation_index": saturation.get("governance_saturation_index"),
        "governance_saturation_band": saturation.get("governance_saturation_band"),
        "expansion_pressure": expansion,
        "expansion_pressure_detected": expansion.get("expansion_pressure_detected"),
        "steady_state_continuity": continuity,
        "steady_state_streak_days": continuity.get("steady_state_streak_days"),
        "steady_state_band": continuity.get("steady_state_band"),
        "operational_closure": closure,
        "operational_closure_candidate": closure.get("operational_closure_candidate"),
        "closure_digest_lines": digest_lines,
        "steady_state_digest_silent": bool(
            closure.get("operational_closure_candidate") and len(digest_lines) <= 1,
        ),
    }


__all__ = ["closure_snapshot"]
