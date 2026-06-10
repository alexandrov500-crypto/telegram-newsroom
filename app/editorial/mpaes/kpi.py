"""MPAES KPI snapshot."""

from __future__ import annotations

from app.editorial.mpaes.state import mpaes_snapshot


def mpaes_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, object]:
    snap = mpaes_snapshot(runtime_dir)
    return {
        **snap,
        "core_kpis": {
            "dual_audience_trust": "mpaes_segment_simulation",
            "hub_substitution_rate": "mpaes_hub_map",
            "reference_operator_fit": "reference_male_persona",
            "growth_acquisition_forward_rate": "telegram_analytics",
            "continuity_without_pause": "stability_anti_pause",
        },
    }
