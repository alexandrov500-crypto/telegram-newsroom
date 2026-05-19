from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.editorial.flow_health.category_balance import compute_category_distribution
from bot.editorial.flow_health.digest_discipline import compute_digest_dependency
from bot.editorial.flow_health.newsroom_mode import classify_newsroom_mode
from bot.editorial.flow_health.predictability import compute_predictability_score
from bot.editorial.flow_health.rhythm import compute_rhythm_modulation
from bot.editorial.flow_health.threshold_stability import analyze_threshold_stability
from bot.editorial.flow_health.trends import compute_flow_trends


def operational_calibration_snapshot(
    *,
    db_path: Path | None = None,
    adaptive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bundled rhythm/balance/predictability telemetry for operator digest."""
    rhythm = compute_rhythm_modulation(db_path=db_path)
    category_24 = compute_category_distribution(hours=24, db_path=db_path)
    category_6 = compute_category_distribution(hours=6, db_path=db_path)
    digest_24 = compute_digest_dependency(hours=24)
    digest_6 = compute_digest_dependency(hours=6)
    trends = compute_flow_trends(db_path=db_path)
    threshold = analyze_threshold_stability(adaptive=adaptive)
    predictability = compute_predictability_score(
        rhythm=rhythm,
        category=category_24,
        digest=digest_24,
        threshold=threshold,
        trends=trends,
    )
    mode = classify_newsroom_mode(
        rhythm=rhythm,
        digest=digest_24,
        category=category_24,
        adaptive=adaptive,
    )
    return {
        "rhythm": rhythm,
        "category_balance": category_24,
        "category_balance_6h": category_6,
        "digest_discipline": digest_24,
        "digest_discipline_6h": digest_6,
        "threshold_stability": threshold,
        "predictability": predictability,
        "newsroom_mode": mode,
        "windows": {
            "6h": {"category": category_6, "digest": digest_6},
            "24h": {"category": category_24, "digest": digest_24},
            "72h": trends.get("windows") or {},
        },
    }
