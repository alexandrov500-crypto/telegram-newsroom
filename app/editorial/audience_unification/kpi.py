"""AUH KPI snapshot for /health and observability."""

from __future__ import annotations

from typing import Any

from app.editorial.audience_unification.config import auh_enabled
from app.editorial.audience_unification.state import auh_distribution_snapshot


def auh_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    dist = auh_distribution_snapshot(runtime_dir)
    return {
        "enabled": auh_enabled(),
        "distribution": dist,
        "product_kpis": {
            "save_rate": "track_via_telegram_analytics",
            "reference_forward_rate": "track_via_telegram_analytics",
            "return_frequency_daily": "track_via_subscriber_cohorts",
            "scroll_through_rate": "track_via_engagement_proxy",
        },
        "objective": dist.get("objective"),
    }
