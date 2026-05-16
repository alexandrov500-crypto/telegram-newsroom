"""Runtime drift monitor validation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.conftest import minimal_test_settings
from utils.runtime_drift_monitor import (
    capture_baseline,
    compare_baselines,
    build_drift_report,
    run_drift_check,
    write_drift_report,
)


def test_config_drift_detected(tmp_path: Path) -> None:
    s1 = minimal_test_settings(worker_retry_safe=False)
    s2 = minimal_test_settings(worker_retry_safe=True)
    b = capture_baseline(s1, output_dir=tmp_path / "od")
    c = capture_baseline(s2, output_dir=tmp_path / "od")
    findings = compare_baselines(b, c)
    assert any(f.category == "config_drift" for f in findings)


def test_wal_growth_warning(tmp_path: Path) -> None:
    s = minimal_test_settings()
    base = capture_baseline(s, output_dir=tmp_path / "od")
    b = replace(base, wal_bytes=2_000_000)
    c = replace(base, wal_bytes=5_000_000)
    findings = compare_baselines(b, c, wal_warn_pct=50.0)
    assert any(f.category == "wal_growth" for f in findings)


def test_drift_report_written(tmp_path: Path) -> None:
    s = minimal_test_settings()
    b = capture_baseline(s, output_dir=tmp_path / "od")
    report = run_drift_check(s, b, output_dir=tmp_path / "od")
    p = write_drift_report(tmp_path / "drift_report.json", report)
    assert p.is_file()
    assert report["schema_version"] == 1
