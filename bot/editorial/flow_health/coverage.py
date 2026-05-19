from __future__ import annotations

import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _coverage_min_score() -> float:
    try:
        return float(os.getenv("MIN_COVERAGE_SCORE", "0.45"))
    except ValueError:
        return 0.45


def _min_distinct_stories() -> int:
    try:
        return int(os.getenv("MIN_DISTINCT_STORIES_6H", "3"))
    except ValueError:
        return 3


def compute_coverage_score(*, hours: int = 6, db_path: Path | None = None) -> dict[str, Any]:
    """
    Lightweight coverage from recent publishes — distinct clusters, sources, tags.
    No ML; uses published_posts + pending cluster linkage when available.
    """
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    clusters: set[int] = set()
    sources: set[str] = set()
    tags: Counter[str] = Counter()
    regions: set[str] = set()
    publish_count = 0
    publish_hours: set[int] = set()

    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT p.cluster_id, p.headline, p.topics_json, p.published_at,
                       pn.source AS news_source
                FROM published_posts p
                LEFT JOIN pending_news pn ON pn.id = p.pending_news_id
                WHERE p.published_at >= datetime('now', ?)
                ORDER BY p.published_at DESC
                LIMIT 80
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for row in rows:
                publish_count += 1
                if row["cluster_id"] is not None:
                    clusters.add(int(row["cluster_id"]))
                try:
                    import json

                    topic_list = json.loads(row["topics_json"] or "[]")[:12]
                    for t in topic_list:
                        tag = str(t).lower()[:40]
                        tags[tag] += 1
                        if any(
                            k in tag
                            for k in (
                                "europe",
                                "asia",
                                "america",
                                "africa",
                                "middle",
                                "ukraine",
                                "china",
                                "us ",
                                "eu ",
                            )
                        ):
                            regions.add(tag[:24])
                except (json.JSONDecodeError, TypeError):
                    pass
                ns = row["news_source"]
                if ns:
                    sources.add(str(ns).strip().lower()[:80])
                hl = row["headline"]
                if hl and not ns:
                    sources.add(str(hl)[:24].lower())
                try:
                    ts = str(row["published_at"] or "")[:13]
                    if "T" in ts:
                        publish_hours.add(int(ts.split("T", 1)[1][:2]))
                except (ValueError, IndexError):
                    pass
    except sqlite3.OperationalError:
        pass

    distinct_clusters = len(clusters)
    distinct_sources = len(sources)
    distinct_tags = len(tags)
    temporal_spread = min(1.0, len(publish_hours) / 3.0)
    regional_spread = min(1.0, len(regions) / 3.0)

    cluster_component = min(1.0, distinct_clusters / max(1, _min_distinct_stories()))
    source_component = min(1.0, distinct_sources / 4.0)
    tag_component = min(1.0, len(tags) / 8.0)
    volume_component = min(1.0, publish_count / max(1, int(os.getenv("MIN_PUBLISH_PER_6H", "3"))))

    coverage_score = round(
        cluster_component * 0.38
        + source_component * 0.22
        + tag_component * 0.18
        + temporal_spread * 0.12
        + regional_spread * 0.05
        + volume_component * 0.05,
        3,
    )

    try:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cadence = compute_cadence_health(db_path=db_path)
    except Exception:
        cadence = {}

    return {
        "coverage_score": coverage_score,
        "distinct_story_clusters": distinct_clusters,
        "distinct_sources": distinct_sources,
        "distinct_tags": distinct_tags,
        "distinct_regions": len(regions),
        "temporal_spread": round(temporal_spread, 3),
        "publish_count": publish_count,
        "coverage_sufficient": coverage_score >= _coverage_min_score()
        and distinct_clusters >= _min_distinct_stories(),
        "min_coverage_score": _coverage_min_score(),
        "min_distinct_stories": _min_distinct_stories(),
        "cadence_health": cadence.get("cadence_health"),
    }
