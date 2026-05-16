"""Trend analysis determinism."""

from __future__ import annotations

from utils.operational_trends import TrendSample, analyze_trends, rolling_baseline


def _samples() -> list[TrendSample]:
    return [
        TrendSample(captured_at="2026-05-01T00:00:00Z", wal_bytes=1_000_000, evidence_dir_bytes=10_000_000),
        TrendSample(captured_at="2026-05-08T00:00:00Z", wal_bytes=2_000_000, evidence_dir_bytes=20_000_000),
        TrendSample(captured_at="2026-05-15T00:00:00Z", wal_bytes=4_000_000, evidence_dir_bytes=40_000_000),
    ]


def test_rolling_baseline_computed() -> None:
    b = rolling_baseline(_samples(), window=3)
    assert b["wal_bytes"] > 0


def test_wal_trend_rising() -> None:
    r = analyze_trends(_samples())
    assert r["trends"]["wal_growth"]["direction"] == "rising"


def test_empty_samples_hints() -> None:
    r = analyze_trends([])
    assert r["sample_count"] == 0
    assert r["maintenance_hints"]
