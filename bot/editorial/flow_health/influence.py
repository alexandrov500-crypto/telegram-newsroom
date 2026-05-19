from __future__ import annotations

from typing import Any


def compute_active_influences(
    *,
    adaptive: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Advisory visibility into which heuristics materially affect behavior now.
    """
    influences: list[dict[str, str | float]] = []

    if adaptive:
        relax = adaptive.get("relaxation") or {}
        scale = float(relax.get("effective_scale") or 0)
        if scale > 0.05:
            influences.append({"name": "relaxation_budget", "contribution": round(scale, 3)})
        if adaptive.get("starvation_active"):
            influences.append({"name": "cadence_floor", "contribution": 0.12})
        cluster_d = float(adaptive.get("cluster_similarity_threshold") or 0.72) - 0.72
        if abs(cluster_d) > 0.02:
            influences.append({"name": "cluster_threshold", "contribution": round(cluster_d, 3)})

        rm = float(relax.get("rhythm_multiplier") or 1.0)
        if rm < 0.98:
            influences.append({"name": "rhythm_dampen", "contribution": round(rm - 1.0, 3)})
        elif rm > 1.02:
            influences.append({"name": "rhythm_nudge", "contribution": round(rm - 1.0, 3)})

    cal = calibration or {}
    rhythm = cal.get("rhythm") or {}
    if rhythm.get("surge_active"):
        influences.append({"name": "surge_balance", "contribution": 0.1})
    if rhythm.get("medium_cycle_active"):
        influences.append({"name": "responsiveness", "contribution": 0.08})

    vit = cal if cal.get("vitality") else (cal.get("vitality") or {})
    if isinstance(vit, dict) and vit.get("responsiveness", {}).get("medium_cycle_active"):
        influences.append({"name": "medium_cycle", "contribution": 0.08})

    deg = degradation or {}
    if deg.get("mode") and deg.get("mode") != "NORMAL":
        influences.append(
            {
                "name": f"degradation_{deg.get('mode')}",
                "contribution": -float(deg.get("modulation_scale") or 1.0) + 1.0,
            },
        )

    influences.sort(key=lambda x: abs(float(x.get("contribution", 0))), reverse=True)
    top = influences[:6]

    formatted: list[str] = []
    for i in top:
        c = float(i["contribution"])
        formatted.append(f"{i['name']} {c:+.3f}")

    return {
        "active_influences": top,
        "influence_summary": formatted,
        "influence_count": len(influences),
    }
