"""Operational health scoring (deterministic; read-only)."""

from __future__ import annotations

from typing import Any, Literal

HealthStatus = Literal["HEALTHY", "DEGRADED", "WARNING", "HIGH_RISK"]


def _clamp_score(score: int) -> int:
    return max(0, min(100, score))


def compute_health_score(
    *,
    retry_burst: int,
    retry_threshold: int,
    wal_bytes: int,
    evidence_bytes: int,
    drift_findings: int,
    scheduler_overlap: int,
    backup_risk: str,
    unsafe_config_count: int,
    trend_anomaly_count: int,
) -> dict[str, Any]:
    """Higher score = healthier (100 best)."""
    score = 100
    dimensions: dict[str, str] = {}

    if retry_burst >= retry_threshold:
        score -= 35
        dimensions["retry_health"] = "HIGH_RISK"
    elif retry_burst >= retry_threshold // 2:
        score -= 15
        dimensions["retry_health"] = "WARNING"
    else:
        dimensions["retry_health"] = "HEALTHY"

    if wal_bytes > 268_435_456:
        score -= 25
        dimensions["wal_hygiene"] = "HIGH_RISK"
    elif wal_bytes > 64_000_000:
        score -= 10
        dimensions["wal_hygiene"] = "WARNING"
    else:
        dimensions["wal_hygiene"] = "HEALTHY"

    if evidence_bytes > 500_000_000:
        score -= 20
        dimensions["retention_hygiene"] = "WARNING"
    else:
        dimensions["retention_hygiene"] = "HEALTHY"

    if drift_findings >= 5:
        score -= 20
        dimensions["drift_pressure"] = "WARNING"
    elif drift_findings > 0:
        score -= 8
        dimensions["drift_pressure"] = "DEGRADED"
    else:
        dimensions["drift_pressure"] = "HEALTHY"

    if scheduler_overlap > 2:
        score -= 15
        dimensions["runtime_stability"] = "WARNING"
    elif scheduler_overlap > 0:
        score -= 5
        dimensions["runtime_stability"] = "DEGRADED"
    else:
        dimensions["runtime_stability"] = "HEALTHY"

    if backup_risk == "HIGH":
        score -= 25
        dimensions["recovery_readiness"] = "HIGH_RISK"
    elif backup_risk == "MEDIUM":
        score -= 10
        dimensions["recovery_readiness"] = "WARNING"
    else:
        dimensions["recovery_readiness"] = "HEALTHY"

    if unsafe_config_count > 0:
        score -= min(30, 10 * unsafe_config_count)
        dimensions["maintenance_discipline"] = "WARNING"

    if trend_anomaly_count >= 3:
        score -= 10
        dimensions.setdefault("maintenance_discipline", "DEGRADED")

    score = _clamp_score(score)
    status: HealthStatus = "HEALTHY"
    if score < 50:
        status = "HIGH_RISK"
    elif score < 65:
        status = "WARNING"
    elif score < 80:
        status = "DEGRADED"

    return {
        "schema_version": 1,
        "health_score": score,
        "status": status,
        "dimensions": dimensions,
    }
