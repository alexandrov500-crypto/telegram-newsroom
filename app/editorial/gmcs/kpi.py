"""GMCS KPI snapshot."""

from __future__ import annotations

from app.editorial.gmcs.state import gmcs_snapshot


def gmcs_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, object]:
    return {
        **gmcs_snapshot(runtime_dir),
        "core_kpis": {
            "market_dominance_index": "gmcs_mdi",
            "ecosystem_win_rate": "competitive_simulator",
            "channels_substituted_vs_ecosystem": "ecosystem_registry",
        },
    }
