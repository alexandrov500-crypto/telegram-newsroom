from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from bot.editorial.flow_health.category_balance import compute_category_distribution
from bot.editorial.flow_health.coverage import compute_coverage_score
from bot.editorial.flow_health.longtail import longtail_activity_summary
from bot.editorial.flow_health.novelty_pressure import compute_novelty_pressure


def compute_editorial_vitality(
    *,
    db_path: Path | None = None,
    cadence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Heuristic editorial aliveness (0–1) — distinct from operational predictability.
    """
    coverage = compute_coverage_score(db_path=db_path)
    category = compute_category_distribution(hours=72, db_path=db_path)
    novelty = compute_novelty_pressure(hours=24, db_path=db_path)
    longtail = longtail_activity_summary(hours=72, db_path=db_path)

    if cadence is None:
        try:
            from bot.editorial.flow_health.cadence import compute_cadence_health

            cadence = compute_cadence_health(db_path=db_path)
        except Exception:
            cadence = {}

    distinct_clusters = int(coverage.get("distinct_story_clusters") or 0)
    distinct_sources = int(coverage.get("distinct_sources") or 0)
    temporal = float(coverage.get("temporal_spread") or 0)
    title_novelty = float(novelty.get("title_novelty_rate") or 0.5)

    bucket_counts = category.get("bucket_counts") or {}
    total_cat = max(1, sum(bucket_counts.values()))
    entropy = 0.0
    for c in bucket_counts.values():
        p = c / total_cat
        if p > 0:
            entropy -= p * math.log(p + 1e-9)
    max_ent = math.log(max(2, len(bucket_counts)))
    category_entropy = min(1.0, entropy / max_ent) if max_ent else 0.5

    narrative_emergence = min(
        1.0,
        (distinct_clusters / 5.0) * 0.5 + float(novelty.get("pending_distinct_clusters") or 0) / 8.0 * 0.5,
    )
    longtail_presence = float(longtail.get("longtail_share") or 0)
    medium_continuity = min(1.0, temporal * 0.6 + float(cadence.get("actual_6h") or 0) / 6.0 * 0.4)

    score = round(
        title_novelty * 0.22
        + narrative_emergence * 0.22
        + category_entropy * 0.18
        + min(1.0, distinct_sources / 5.0) * 0.12
        + longtail_presence * 0.14
        + medium_continuity * 0.12,
        3,
    )
    band = "healthy"
    if score < 0.45:
        band = "stale"
    elif score < 0.62:
        band = "muted"

    return {
        "editorial_vitality_score": score,
        "vitality_band": band,
        "narrative_emergence": round(narrative_emergence, 3),
        "category_entropy": round(category_entropy, 3),
        "longtail_presence": round(longtail_presence, 3),
        "title_novelty_rate": title_novelty,
        "distinct_clusters_6h": distinct_clusters,
    }
