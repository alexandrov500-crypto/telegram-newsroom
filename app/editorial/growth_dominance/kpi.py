"""EGDL KPI snapshot — growth + editorial + system metrics."""

from __future__ import annotations

from typing import Any

from app.editorial.growth_dominance.config import egdl_enabled, gravity_must_publish_threshold
from app.editorial.growth_dominance.frequency_strategy import resolve_frequency_plan
from app.editorial.growth_dominance.state import today_gravity_stats
from app.editorial.stability.slo import stability_slo_snapshot


def egdl_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    stats = today_gravity_stats(runtime_dir)
    scores = []
    try:
        from app.editorial.growth_dominance.state import load_state

        day = dict((load_state(runtime_dir).get("days") or {}).get(
            __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime())
        ) or {})
        scores = [float(x) for x in (day.get("gravity_scores") or [])]
    except Exception:
        pass

    high_pct = 0.0
    if scores:
        high_pct = round(sum(1 for s in scores if s >= gravity_must_publish_threshold()) / len(scores) * 100, 1)

    freq = resolve_frequency_plan(
        high_gravity_events_today=int(stats.get("high_gravity_count") or 0),
        avg_gravity_today=float(stats.get("avg_gravity") or 0),
        posts_today=int(stats.get("posts_published") or 0),
    )

    stability = stability_slo_snapshot(runtime_dir)

    return {
        "enabled": egdl_enabled(),
        "growth_kpis": {
            "forward_rate_primary": "track_via_telegram_analytics",
            "save_rate": "track_via_telegram_analytics",
            "return_frequency_24h": "track_via_subscriber_cohorts",
        },
        "editorial_kpis": {
            "gravity_avg_today": stats.get("avg_gravity"),
            "pct_posts_gte_80_gravity": high_pct,
            "loop_distribution": stats.get("loop_counts"),
            "frequency_mode": freq.to_dict(),
        },
        "system_kpis": {
            "continuity_score": stability.get("slo", {}).get("continuity_score"),
            "gap_slo_ok": stability.get("slo", {}).get("gap_slo_ok"),
            "cluster_diversity_index": stats.get("loop_counts"),
        },
        "objective": "maximize_information_dominance_per_attention_unit",
    }
