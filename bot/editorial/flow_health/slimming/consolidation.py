from __future__ import annotations

from typing import Any

# Known overlap groups — advisory consolidation candidates only.
_OVERLAP_GROUPS: list[dict[str, Any]] = [
    {
        "group": "cadence_rhythm",
        "heuristics": ["cadence_health", "rhythm_modulation", "publish_floor"],
        "note": "All modulate publish throughput timing",
    },
    {
        "group": "vitality_novelty",
        "heuristics": ["editorial_vitality", "novelty_pressure", "coverage_score"],
        "note": "Freshness and narrative diversity signals overlap",
    },
    {
        "group": "trust_realism",
        "heuristics": ["operator_trust_index", "operational_realism_index", "predictability_score"],
        "note": "Operator confidence vs editorial aliveness",
    },
    {
        "group": "surge_responsiveness",
        "heuristics": ["surge_balance", "medium_cycle_responsiveness"],
        "note": "Both increase rhythm during active news cycles",
    },
]


def analyze_heuristic_consolidation(
    *,
    influences: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Identify redundant or low-effect heuristics — no automatic removal."""
    candidates: list[dict[str, str]] = []
    for grp in _OVERLAP_GROUPS:
        candidates.append(
            {
                "group": grp["group"],
                "recommendation": "review_for_future_merge",
                "note": str(grp["note"]),
            },
        )

    inactive: list[str] = []
    saturated: list[str] = []
    negligible: list[str] = []

    if adaptive:
        relax = adaptive.get("relaxation") or {}
        used = float(relax.get("relaxation_budget_used") or 0)
        mx = float(relax.get("relaxation_budget_max") or 0.25)
        if used >= mx * 0.92:
            saturated.append("relaxation_budget")
        elif used < mx * 0.15 and not adaptive.get("starvation_active"):
            negligible.append("relaxation_budget")
        if not adaptive.get("starvation_active"):
            inactive.append("publish_floor_modulation")

    infl_names = [str(i.get("name", "")) for i in (influences or {}).get("active_influences") or []]
    if len(infl_names) <= 2:
        negligible.extend(["longtail_nudge", "category_recovery_nudge"])

    density = len(infl_names) + len(saturated)
    return {
        "consolidation_candidates": candidates[:6],
        "inactive_heuristics": inactive,
        "saturated_heuristics": saturated,
        "negligible_effect_heuristics": negligible,
        "heuristic_density": density,
    }
