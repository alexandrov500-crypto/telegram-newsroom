from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from bot.editorial.priority.balance import topic_bucket

# Long-tail editorial lanes (tag substring heuristics — no taxonomy redesign).
_LONGTAIL_NEEDLES: dict[str, tuple[str, ...]] = {
    "science": ("science", "research", "space", "biology", "physics"),
    "climate": ("climate", "weather", "wildfire", "flood", "emission"),
    "regional": ("africa", "latin", "pacific", "balkans", "caucasus"),
    "cyber": ("cyber", "ransomware", "hack", "breach", "malware"),
    "infrastructure": ("infrastructure", "outage", "grid", "rail", "port"),
}


def classify_longtail(tags: list[str]) -> str | None:
    keys = " ".join(str(t).lower() for t in tags)
    for lane, needles in _LONGTAIL_NEEDLES.items():
        if any(n in keys for n in needles):
            return lane
    bucket = topic_bucket(tags, None)
    if bucket in ("energy", "technology") and bucket not in keys:
        return None
    return None


def longtail_activity_summary(*, hours: int = 72, db_path: Path | None = None) -> dict[str, Any]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    lanes: Counter[str] = Counter()
    total = 0
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT topics_json FROM published_posts
                WHERE published_at >= datetime('now', ?)
                LIMIT 80
                """,
                (f"-{hours} hours",),
            ).fetchall()
        for row in rows:
            total += 1
            try:
                tags = json.loads(row[0] or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            lane = classify_longtail(tags)
            if lane:
                lanes[lane] += 1
    except sqlite3.OperationalError:
        pass

    longtail_count = sum(lanes.values())
    share = longtail_count / max(1, total)
    absent = [lane for lane in _LONGTAIL_NEEDLES if lanes.get(lane, 0) == 0]

    return {
        "longtail_publish_count": longtail_count,
        "longtail_share": round(share, 3),
        "longtail_lanes": dict(lanes),
        "absent_lanes": absent[:5],
        "hours": hours,
    }


def longtail_coverage_adjustment(
    tags: list[str],
    *,
    cadence_health: float | None = None,
) -> float:
    """
    Soft priority nudge for rare lanes during healthy cadence — never forces publish.
    """
    try:
        from bot.editorial.flow_health.degradation import gates_for_current_mode

        if not gates_for_current_mode().get("longtail_nudges", True):
            return 0.0
    except Exception:
        pass
    if os.getenv("LONGTAIL_PROTECTION_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return 0.0
    try:
        if cadence_health is None:
            from bot.editorial.flow_health.cadence import compute_cadence_health

            cadence_health = float(compute_cadence_health().get("cadence_health") or 1.0)
        if cadence_health < 0.4:
            return 0.0
        from bot.editorial.flow_health.floor import is_publish_floor_active

        if is_publish_floor_active():
            return 0.0
        lane = classify_longtail(tags)
        if not lane:
            return 0.0
        summary = longtail_activity_summary(hours=72)
        if lane in summary.get("absent_lanes", []):
            return 0.05
        if float(summary.get("longtail_share") or 0) < 0.08:
            return 0.03
    except Exception:
        pass
    return 0.0
