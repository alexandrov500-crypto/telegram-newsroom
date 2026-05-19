from __future__ import annotations

import os
import sqlite3
from typing import Any


def detect_news_surge(*, db_path: str | None = None) -> dict[str, Any]:
    """
    Lightweight surge heuristic — ingestion spike + cluster novelty.
    Used to relax rhythm dampening during breaking periods (not spam mode).
    """
    try:
        from bot.editorial.flow_health.funnel import funnel_summary

        summary = funnel_summary()
        counters = summary.get("counters") or {}
        fetched = int(counters.get("FETCHED", 0))
        clustered = int(counters.get("CLUSTERED", 0))
        published = int(counters.get("PUBLISHED", 0))
    except Exception:
        return {"surge_active": False, "reason": "funnel_unavailable"}

    try:
        min_fetched = int(os.getenv("SURGE_MIN_FETCHED_6H", "60"))
    except ValueError:
        min_fetched = 60
    try:
        cluster_ratio_min = float(os.getenv("SURGE_CLUSTER_RATIO", "0.35"))
    except ValueError:
        cluster_ratio_min = 0.35

    cluster_ratio = clustered / fetched if fetched else 0.0
    distinct_clusters = _distinct_recent_clusters(db_path)

    surge = (
        fetched >= min_fetched
        and cluster_ratio >= cluster_ratio_min
        and distinct_clusters >= int(os.getenv("SURGE_MIN_DISTINCT_CLUSTERS", "8"))
        and published < max(3, int(fetched * 0.08))
    )

    return {
        "surge_active": surge,
        "fetched_6h": fetched,
        "cluster_ratio": round(cluster_ratio, 3),
        "distinct_clusters_6h": distinct_clusters,
        "published_6h": published,
        "reason": "breaking_ingestion_surge" if surge else "normal",
    }


def _distinct_recent_clusters(db_path: str | None) -> int:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT cluster_id) FROM pending_news
                WHERE cluster_id IS NOT NULL
                  AND created_at >= datetime('now', '-6 hours')
                """,
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0


def surge_rhythm_multiplier(base_multiplier: float, surge: dict[str, Any]) -> float:
    """Reduce smoothing suppression during surges — still bounded."""
    if not surge.get("surge_active"):
        return base_multiplier
    try:
        boost = float(os.getenv("SURGE_RHYTHM_BOOST", "0.12"))
    except ValueError:
        boost = 0.12
    if base_multiplier < 1.0:
        return min(1.0, base_multiplier + boost)
    return min(1.15, base_multiplier + boost * 0.5)
