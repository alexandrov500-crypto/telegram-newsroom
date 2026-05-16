"""Tests for offline ops analytics (P2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.ops_analytics import (
    ANALYTICS_SCHEMA_VERSION,
    archive_snapshots,
    build_analytics_summary,
    build_visualization_bundle,
    load_snapshot_series_safe,
    svg_sparkline,
    verify_archive_file,
)
from utils.ops_tooling import persist_snapshot, OPS_SNAPSHOT_SCHEMA_VERSION

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ops_history"


def test_load_series_from_fixtures() -> None:
    series, skipped = load_snapshot_series_safe(FIXTURES, limit=10)
    assert len(series) == 3
    assert skipped == []


def test_analytics_summary_deterministic() -> None:
    a = build_analytics_summary(FIXTURES, limit=10)
    b = build_analytics_summary(FIXTURES, limit=10)
    assert a["trends"]["publish_retries"]["delta_total"] == b["trends"]["publish_retries"]["delta_total"]
    assert a["snapshot_count"] == 3


def test_corrupt_snapshot_skipped(tmp_path: Path) -> None:
    hist = tmp_path / "h"
    hist.mkdir()
    (hist / "ops_metrics_bad.json").write_text("{", encoding="utf-8")
    persist_snapshot(
        hist,
        {
            "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_kind": "ops_metrics",
            "read_only": True,
            "no_telegram_api_calls": True,
            "no_redis_mutations": True,
            "captured_at": "2026-05-16T10:00:00Z",
            "diagnostics": {"metrics": {"publishes": 1}},
        },
        filename="ops_metrics_ok.json",
    )
    series, skipped = load_snapshot_series_safe(hist)
    assert len(series) == 1
    assert skipped == ["ops_metrics_bad.json"]


def test_svg_sparkline_stable() -> None:
    s1 = svg_sparkline([1.0, 2.0, 1.5], title="t")
    s2 = svg_sparkline([1.0, 2.0, 1.5], title="t")
    assert s1 == s2
    assert "<svg" in s1


def test_visualization_bundle() -> None:
    summary = build_analytics_summary(FIXTURES, limit=10)
    charts = build_visualization_bundle(summary)
    assert "publish_retries.svg" in charts
    assert charts["publish_retries.svg"].startswith("<svg")


def test_archive_roundtrip(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    arch = tmp_path / "arch"
    hist.mkdir()
    old_ts = "2020-01-01T00:00:00Z"
    persist_snapshot(
        hist,
        {
            "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_kind": "ops_metrics",
            "read_only": True,
            "no_telegram_api_calls": True,
            "no_redis_mutations": True,
            "captured_at": old_ts,
            "diagnostics": {"metrics": {"publishes": 9}},
        },
        filename="ops_metrics_old.json",
    )
    result = archive_snapshots(hist, arch, older_than_days=1)
    assert result["archived"] == 1
    gz = next(arch.rglob("*.json.gz"))
    assert verify_archive_file(gz)
    assert not (hist / "ops_metrics_old.json").exists()


def test_cli_aggregate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess
    import sys

    hist = tmp_path / "hist"
    rep = tmp_path / "rep"
    shutil.copytree(FIXTURES, hist)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/ops_analytics_aggregate.py",
            "--history-dir",
            str(hist),
            "--reports-dir",
            str(rep),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads((rep / "analytics_summary.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == ANALYTICS_SCHEMA_VERSION
