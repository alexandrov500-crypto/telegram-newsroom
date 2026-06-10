"""UEOS KPI snapshot for /health."""

from __future__ import annotations

from typing import Any

from app.editorial.unified_operating_system.config import ueos_enabled
from app.editorial.unified_operating_system.state import ueos_state_snapshot


def ueos_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    state = ueos_state_snapshot(runtime_dir)
    return {
        "enabled": ueos_enabled(),
        "ueos_state": state,
        "product_truth_kpis": {
            "single_channel_substitution_rate": "forwards + saves + return_visits/day",
            "digest_completion_rate": "track_via_engagement_proxy",
            "pct_users_2plus_posts_per_day": "track_via_subscriber_cohorts",
        },
        "objective": state.get("objective"),
    }
