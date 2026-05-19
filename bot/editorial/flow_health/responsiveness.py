from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def compute_medium_cycle_responsiveness(*, db_path: Path | None = None) -> dict[str, Any]:
    """
    Sustained developing-story detection — soft cadence suppression relief.
    No planning/memory; uses pending cluster density only.
    """
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    developing_clusters = 0
    distinct_clusters = 0
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT cluster_id, COUNT(*) AS c FROM pending_news
                WHERE cluster_id IS NOT NULL
                  AND created_at >= datetime('now', '-18 hours')
                GROUP BY cluster_id
                HAVING c >= 2
                """,
            ).fetchall()
            developing_clusters = len(rows)
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT cluster_id) FROM pending_news
                WHERE cluster_id IS NOT NULL
                  AND created_at >= datetime('now', '-18 hours')
                """,
            ).fetchone()
            distinct_clusters = int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        pass

    try:
        from bot.editorial.flow_health.funnel import funnel_summary

        fetched = int((funnel_summary().get("counters") or {}).get("FETCHED", 0))
        published = int((funnel_summary().get("counters") or {}).get("PUBLISHED", 0))
    except Exception:
        fetched, published = 0, 0

    try:
        min_developing = int(os.getenv("RESPONSIVENESS_MIN_DEVELOPING_CLUSTERS", "3"))
    except ValueError:
        min_developing = 3

    active = (
        developing_clusters >= min_developing
        and distinct_clusters >= min_developing + 1
        and fetched >= 25
        and published < max(4, int(fetched * 0.12))
    )

    try:
        boost = float(os.getenv("RESPONSIVENESS_RHYTHM_BOOST", "0.08"))
    except ValueError:
        boost = 0.08

    multiplier = 1.0
    if active:
        multiplier = min(1.12, 1.0 + boost)

    return {
        "medium_cycle_active": active,
        "developing_story_clusters": developing_clusters,
        "distinct_pending_clusters": distinct_clusters,
        "responsiveness_multiplier": round(multiplier, 4),
        "reason": "evolving_story_cycle" if active else "normal",
    }


def apply_responsiveness_to_rhythm(base_multiplier: float, resp: dict[str, Any]) -> float:
    if not resp.get("medium_cycle_active"):
        return base_multiplier
    mult = float(resp.get("responsiveness_multiplier") or 1.0)
    if base_multiplier < 1.0:
        return min(1.0, base_multiplier + (mult - 1.0))
    return min(1.12, base_multiplier * mult)
