from __future__ import annotations

from typing import Any


def estimate_maintenance_burden(
    *,
    complexity: dict[str, Any],
    persistence: dict[str, Any],
    loops: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    """Practical sustainability estimates — advisory scores 0–10 (lower is better)."""
    loop_burden = min(10, complexity.get("background_loop_count", 0) * 0.8)
    storage_burden = min(10, complexity.get("ops_table_count", 0) * 0.25)
    alert_burden = min(10, len(signals.get("overlap_groups", [])) * 1.5)
    operator_burden = min(10, complexity.get("operator_command_count", 0) * 0.35)
    debug_burden = min(
        10,
        len([l for l in loops.get("loops", []) if l.get("tier") == "debug"]) * 1.2,
    )

    unclaimed = len(persistence.get("unclaimed_ops_tables") or [])
    ownership_burden = min(10, unclaimed * 2)

    total = (
        loop_burden * 0.25
        + storage_burden * 0.2
        + alert_burden * 0.2
        + operator_burden * 0.2
        + debug_burden * 0.1
        + ownership_burden * 0.05
    )

    sustainability = "good"
    if total >= 7:
        sustainability = "strained"
    elif total >= 4.5:
        sustainability = "moderate"

    return {
        "overall_burden_score": round(total, 2),
        "sustainability": sustainability,
        "components": {
            "loop_scheduler": round(loop_burden, 2),
            "storage_tables": round(storage_burden, 2),
            "alert_overlap": round(alert_burden, 2),
            "operator_surface": round(operator_burden, 2),
            "debug_loops": round(debug_burden, 2),
            "ownership_gaps": round(ownership_burden, 2),
        },
        "top_reduction_levers": _reduction_levers(complexity, loops, signals),
    }


def _reduction_levers(
    complexity: dict[str, Any],
    loops: dict[str, Any],
    signals: dict[str, Any],
) -> list[str]:
    levers: list[str] = []
    if complexity.get("background_loop_count", 0) > 8:
        levers.append("Disable non-pilot loops via RUNTIME_PROFILE=minimal_pilot")
    if complexity.get("operator_command_count", 0) > 18:
        levers.append("Route routine ops through /operator_digest only")
    if len(signals.get("overlap_groups", [])) >= 4:
        levers.append("Apply signal dedupe in operator UX (enabled via OPS_CONSOLIDATION_DEDUPE)")
    for rec in loops.get("rationalization_recommendations") or []:
        levers.append(rec)
    return levers[:6]
