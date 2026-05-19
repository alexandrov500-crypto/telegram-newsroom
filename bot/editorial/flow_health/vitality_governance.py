from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.editorial.flow_health.longtail import longtail_activity_summary
from bot.editorial.flow_health.novelty_pressure import compute_novelty_pressure
from bot.editorial.flow_health.realism import compute_operational_realism_index
from bot.editorial.flow_health.responsiveness import compute_medium_cycle_responsiveness
from bot.editorial.flow_health.stagnation import detect_stagnation_risk
from bot.editorial.flow_health.vitality import compute_editorial_vitality


def vitality_governance_snapshot(
    *,
    db_path: Path | None = None,
    cadence: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    trust_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Editorial vitality bundle — lazy, fail-open."""
    vitality = compute_editorial_vitality(db_path=db_path, cadence=cadence)
    novelty = compute_novelty_pressure(hours=24, db_path=db_path)
    novelty_48 = compute_novelty_pressure(hours=48, db_path=db_path)
    longtail = longtail_activity_summary(hours=72, db_path=db_path)
    responsiveness = compute_medium_cycle_responsiveness(db_path=db_path)
    stagnation = detect_stagnation_risk(
        vitality=vitality,
        cadence=cadence,
        novelty=novelty_48,
    )

    if coverage is None:
        from bot.editorial.flow_health.coverage import compute_coverage_score

        coverage = compute_coverage_score(db_path=db_path)
    if cadence is None:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cadence = compute_cadence_health(db_path=db_path)

    realism = compute_operational_realism_index(
        vitality=vitality,
        stagnation=stagnation,
        novelty=novelty,
        responsiveness=responsiveness,
        longtail=longtail,
        cadence=cadence,
        coverage=coverage,
        trust_index=trust_index,
    )

    freshness_trend = "stable"
    if float(novelty.get("novelty_pressure_score") or 0) >= 0.55:
        freshness_trend = "declining"
    elif float(novelty.get("title_novelty_rate") or 0) >= 0.55:
        freshness_trend = "healthy"

    return {
        "vitality": vitality,
        "stagnation": stagnation,
        "novelty_pressure": novelty,
        "longtail": longtail,
        "responsiveness": responsiveness,
        "realism": realism,
        "freshness_trend": freshness_trend,
    }
