"""UGSOL KPI snapshot."""

from __future__ import annotations

from app.editorial.ugsol.state import ugsol_snapshot


def ugsol_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, object]:
    snap = ugsol_snapshot(runtime_dir)
    return {
        **snap,
        "core_kpis": {
            "max_gap_min": "content_flow_governor",
            "imri_sustained_80": "imri_dominance_mode",
            "forward_rate": "feedback_reinjection",
            "return_rate": "feedback_reinjection",
            "substitution_rate": "imri_formula",
            "habit_rate": "ccd_habit_anchors",
            "multi_persona_resonance": "audience_dominance_balancer",
        },
        "stability_targets": {
            "max_gap_minutes": 90,
            "zero_silent_periods": True,
        },
        "growth_targets": {
            "imri_dominance": 80,
            "forward_rate_up": True,
            "return_rate_up": True,
        },
    }
