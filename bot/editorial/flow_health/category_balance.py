from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from bot.editorial.priority.balance import TOPIC_BUCKETS, topic_bucket


def _dominance_threshold() -> float:
    try:
        return float(os.getenv("CATEGORY_DOMINANCE_THRESHOLD", "0.55"))
    except ValueError:
        return 0.55


def compute_category_distribution(*, hours: int = 24, db_path: Path | None = None) -> dict[str, Any]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    buckets: Counter[str] = Counter()
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT topics_json FROM published_posts
                WHERE published_at >= datetime('now', ?)
                ORDER BY published_at DESC LIMIT 60
                """,
                (f"-{hours} hours",),
            ).fetchall()
        for row in rows:
            try:
                tags = json.loads(row["topics_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            buckets[topic_bucket(tags, None)] += 1
    except sqlite3.OperationalError:
        pass

    total = sum(buckets.values()) or 1
    dominant_bucket, dom_count = buckets.most_common(1)[0] if buckets else ("general", 0)
    dominant_ratio = dom_count / total
    all_buckets = set(TOPIC_BUCKETS) | {"general"}
    underrepresented = [b for b in all_buckets if buckets.get(b, 0) / total < 0.12]

    return {
        "bucket_counts": dict(buckets),
        "dominant_bucket": dominant_bucket,
        "dominant_ratio": round(dominant_ratio, 3),
        "imbalanced": dominant_ratio >= _dominance_threshold(),
        "underrepresented": underrepresented,
        "publish_count": total,
        "hours": hours,
    }


def recovery_category_adjustment(
    tags: list[str],
    topic_keys: list[str] | None = None,
) -> float:
    """
    Soft score nudge during publish floor only — never forces publish.
    Returns small additive boost (0–0.06) for underrepresented buckets.
    """
    try:
        from bot.editorial.flow_health.floor import is_publish_floor_active

        if not is_publish_floor_active():
            return 0.0
        try:
            from bot.editorial.flow_health.degradation import gates_for_current_mode

            if not gates_for_current_mode().get("category_recovery_nudges", True):
                return 0.0
        except Exception:
            pass
        if os.getenv("CATEGORY_BALANCE_RECOVERY_ENABLED", "true").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return 0.0
        dist = compute_category_distribution(hours=24)
        bucket = topic_bucket(tags, topic_keys)
        if bucket in dist.get("underrepresented", []):
            return 0.06
        if dist.get("imbalanced") and bucket != dist.get("dominant_bucket"):
            return 0.03
    except Exception:
        pass
    return 0.0
