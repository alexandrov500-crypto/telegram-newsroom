from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from bot.processing.semantic import build_fingerprint, jaccard_similarity


def _title_novelty_rate(headlines: list[str]) -> float:
    if len(headlines) < 2:
        return 1.0
    fps = [build_fingerprint(h)[0] for h in headlines if h]
    if len(fps) < 2:
        return 1.0
    sims: list[float] = []
    for i in range(min(len(fps) - 1, 12)):
        sims.append(jaccard_similarity(fps[i], fps[i + 1]))
    avg_sim = sum(sims) / len(sims) if sims else 0.5
    return round(max(0.0, 1.0 - avg_sim), 3)


def compute_novelty_pressure(*, hours: int = 24, db_path: Path | None = None) -> dict[str, Any]:
    """
    Advisory pressure when volume exists but informational freshness is low.
    Higher score = more pressure to seek novelty (not a publish trigger).
    """
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    headlines: list[str] = []
    sources: Counter[str] = Counter()
    clusters: set[int] = set()

    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT headline, cluster_id, topics_json, pending_news_id
                FROM published_posts
                WHERE published_at >= datetime('now', ?)
                ORDER BY published_at DESC LIMIT 40
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for row in rows:
                if row["headline"]:
                    headlines.append(str(row["headline"]))
                if row["cluster_id"] is not None:
                    clusters.add(int(row["cluster_id"]))
            pending = conn.execute(
                """
                SELECT COUNT(DISTINCT cluster_id) FROM pending_news
                WHERE cluster_id IS NOT NULL
                  AND created_at >= datetime('now', ?)
                """,
                (f"-{hours} hours",),
            ).fetchone()
            pending_distinct = int(pending[0] or 0) if pending else 0
            src_rows = conn.execute(
                """
                SELECT pn.source FROM published_posts p
                JOIN pending_news pn ON pn.id = p.pending_news_id
                WHERE p.published_at >= datetime('now', ?)
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for sr in src_rows:
                if sr[0]:
                    sources[str(sr[0]).lower()[:60]] += 1
    except sqlite3.OperationalError:
        pending_distinct = 0

    title_novelty = _title_novelty_rate(headlines)
    publish_count = len(headlines)
    cluster_emergence = min(1.0, len(clusters) / max(1, publish_count))
    pending_emergence = min(1.0, pending_distinct / max(3, publish_count))

    source_repeat = 0.0
    if sources:
        top = sources.most_common(1)[0][1]
        source_repeat = top / sum(sources.values())

    freshness = title_novelty * 0.45 + cluster_emergence * 0.30 + pending_emergence * 0.25
    novelty_pressure_score = round(max(0.0, min(1.0, 1.0 - freshness + source_repeat * 0.25)), 3)

    return {
        "novelty_pressure_score": novelty_pressure_score,
        "title_novelty_rate": title_novelty,
        "distinct_published_clusters": len(clusters),
        "pending_distinct_clusters": pending_distinct,
        "source_repeat_ratio": round(source_repeat, 3),
        "publish_count": publish_count,
        "low_freshness": novelty_pressure_score >= 0.55,
    }
