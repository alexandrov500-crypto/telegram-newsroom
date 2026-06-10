"""Channel Product KPI snapshot for /health."""

from __future__ import annotations

from typing import Any

from app.editorial.channel_product.config import channel_product_enabled
from app.editorial.channel_product.state import channel_product_snapshot


def channel_product_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    snap = channel_product_snapshot(runtime_dir)
    return {
        "enabled": channel_product_enabled(),
        "channel_product_state": snap,
        "product_truth_kpis": {
            "forwards_per_post": "track_via_telegram_analytics",
            "saves_per_post": "track_via_telegram_analytics",
            "return_visits_per_day": "track_via_subscriber_cohorts",
            "pct_users_2plus_posts_per_day": "track_via_engagement_proxy",
            "digest_completion_rate": "track_via_engagement_proxy",
        },
        "objective": snap.get("objective"),
    }
