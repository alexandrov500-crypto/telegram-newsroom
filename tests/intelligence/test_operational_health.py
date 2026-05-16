"""Health scoring bounds."""

from __future__ import annotations

from utils.operational_health import compute_health_score


def test_healthy_default() -> None:
    h = compute_health_score(
        retry_burst=0,
        retry_threshold=40,
        wal_bytes=0,
        evidence_bytes=0,
        drift_findings=0,
        scheduler_overlap=0,
        backup_risk="LOW",
        unsafe_config_count=0,
        trend_anomaly_count=0,
    )
    assert h["status"] == "HEALTHY"
    assert h["health_score"] >= 80


def test_high_risk_retry_storm() -> None:
    h = compute_health_score(
        retry_burst=50,
        retry_threshold=40,
        wal_bytes=300_000_000,
        evidence_bytes=600_000_000,
        drift_findings=10,
        scheduler_overlap=5,
        backup_risk="HIGH",
        unsafe_config_count=2,
        trend_anomaly_count=5,
    )
    assert h["status"] in ("WARNING", "HIGH_RISK")
    assert h["health_score"] < 65


def test_no_false_critical_on_mild_signals() -> None:
    h = compute_health_score(
        retry_burst=5,
        retry_threshold=40,
        wal_bytes=1_000_000,
        evidence_bytes=50_000_000,
        drift_findings=1,
        scheduler_overlap=0,
        backup_risk="LOW",
        unsafe_config_count=0,
        trend_anomaly_count=1,
    )
    assert h["status"] in ("HEALTHY", "DEGRADED")
