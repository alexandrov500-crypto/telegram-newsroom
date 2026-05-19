from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.editorial.flow_health.adaptive import adaptive_modulation
from bot.editorial.flow_health.cadence import compute_cadence_health
from bot.editorial.flow_health.canary_balance import effective_canary_max_per_hour
from bot.editorial.flow_health.coverage import compute_coverage_score
from bot.editorial.flow_health.duplicate_escape import duplicate_escape_count
from bot.editorial.flow_health.floor import is_publish_floor_active
from bot.editorial.flow_health.funnel import funnel_summary
from bot.editorial.flow_health.recovery import should_run_recovery_digest
from bot.editorial.flow_health.calibration import operational_calibration_snapshot
from bot.editorial.flow_health.governance import governance_snapshot
from bot.editorial.flow_health.trends import compute_flow_trends


def flow_health_snapshot(*, db_path: Path | None = None) -> dict[str, Any]:
    funnel = funnel_summary(db_path=db_path)
    adaptive = adaptive_modulation()
    cadence = compute_cadence_health(db_path=db_path)
    coverage = compute_coverage_score(db_path=db_path)
    calibration = operational_calibration_snapshot(db_path=db_path, adaptive=adaptive)
    governance = governance_snapshot(
        db_path=db_path,
        cadence=cadence,
        coverage=coverage,
        calibration=calibration,
        adaptive=adaptive,
    )
    return {
        "funnel": funnel,
        "adaptive": adaptive,
        "cadence": cadence,
        "canary_balance": effective_canary_max_per_hour(
            cadence_health=float(cadence.get("cadence_health") or 1.0),
        ),
        "coverage": coverage,
        "trends": compute_flow_trends(db_path=db_path),
        "publish_floor_active": is_publish_floor_active(),
        "recovery_digest_pending": should_run_recovery_digest(),
        "duplicate_escapes_24h": duplicate_escape_count(hours=24, db_path=db_path),
        "duplicate_escapes_72h": duplicate_escape_count(hours=72, db_path=db_path),
        "calibration": calibration,
        "governance": governance,
    }
