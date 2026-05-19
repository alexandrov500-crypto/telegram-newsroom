from __future__ import annotations

import json
from pathlib import Path

from bot.editorial.runtime_validation.baseline import (
    append_baseline_record,
    capture_operational_baseline,
    load_baseline_history,
)


def _sample_report() -> dict:
    return {
        "infrastructure_validation_ok": True,
        "checks_passed": 6,
        "checks_total": 7,
        "summary_lines": ["Persistence remains bounded"],
        "persistence": {
            "metrics_json_bytes": 1200,
            "persistence_growth_rate": 0.1,
            "continuity_storage_pressure": 0.2,
            "memory_retention_health": "HEALTHY",
            "bounded_persistence_ok": True,
        },
        "digest": {
            "digest_line_count": 2,
            "digest_noise_drift": 0.0,
            "invisible_digest_stability": True,
            "stewardship_verbosity_pressure": 0.0,
            "quiet_modes": {"invisible_digest": True},
        },
        "scheduler": {
            "scheduler_stability": 1.0,
            "publish_continuity_ok": True,
            "stalled_loops": [],
        },
        "telemetry": {
            "telemetry_growth_rate": 0.3,
            "collector_integrity_ok": True,
            "telemetry_fragmentation_detected": False,
            "canonical_telemetry_stability": True,
        },
        "restart": {
            "recovery_activation_count": 2,
            "recovery_active": False,
            "runtime_restart_health": 0.9,
        },
        "degradation": {
            "degradation_mode": "NORMAL",
            "degraded_runtime_recovery": 0.9,
            "hidden_entropy_observed": False,
            "operational_aging_ok": True,
        },
        "operational_aging": {
            "long_horizon_calm": True,
            "operational_fatigue_detected": False,
            "slow_drift_risk": False,
        },
    }


def test_capture_operational_baseline_shape() -> None:
    b = capture_operational_baseline(_sample_report(), week_id="2026-W01")
    assert b["week_id"] == "2026-W01"
    assert b["persistence"]["bounded_persistence_ok"] is True
    assert b["calmness"]["long_horizon_calm"] is True


def test_append_and_load_baseline(tmp_path: Path) -> None:
    b = capture_operational_baseline(_sample_report(), week_id="2026-W02")
    path = append_baseline_record(b, output_dir=tmp_path)
    assert path.exists()
    hist = load_baseline_history(output_dir=tmp_path, limit=5)
    assert len(hist) == 1
    assert hist[0]["week_id"] == "2026-W02"


def test_baseline_retention_cap(tmp_path: Path) -> None:
    for i in range(95):
        append_baseline_record(
            capture_operational_baseline(_sample_report(), week_id=f"W{i}"),
            output_dir=tmp_path,
        )
    lines = (tmp_path / "weekly_baseline.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 90
