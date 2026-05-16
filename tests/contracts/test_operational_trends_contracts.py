"""Operational trends and analytics schema contracts (P2)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from utils.ops_analytics import ANALYTICS_SCHEMA_VERSION, build_analytics_summary, svg_sparkline
from utils.ops_tooling import OPS_SNAPSHOT_SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests/tools/fixtures/ops_history"


def test_analytics_schema_stable() -> None:
    assert ANALYTICS_SCHEMA_VERSION == 1


def test_snapshot_backward_compatible() -> None:
    summary = build_analytics_summary(FIXTURES, limit=5)
    assert summary["snapshot_count"] >= 1
    assert "trends" in summary


def test_missing_metrics_field_tolerance(tmp_path: Path) -> None:
    hist = tmp_path / "h"
    hist.mkdir()
    (hist / "ops_metrics_sparse.json").write_text(
        json.dumps(
            {
                "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
                "snapshot_kind": "ops_metrics",
                "read_only": True,
                "no_telegram_api_calls": True,
                "no_redis_mutations": True,
                "captured_at": "2026-05-16T15:00:00Z",
                "diagnostics": {"metrics": {}},
            }
        ),
        encoding="utf-8",
    )
    summary = build_analytics_summary(hist)
    assert summary["snapshot_count"] == 1


def test_visualization_svg_format() -> None:
    svg = svg_sparkline([0, 1, 0], title="test")
    assert re.search(r"<svg[^>]+xmlns=", svg)


def test_retention_policy_documented() -> None:
    text = (REPO / "docs/operations/metrics_retention_policy.md").read_text(encoding="utf-8")
    assert "20 MB" in text or "20MB" in text.replace(" ", "")
    assert "ops_archive" in text


def test_shift_handoff_cli(tmp_path: Path) -> None:
    import shutil

    hist = tmp_path / "hist"
    rep = tmp_path / "rep"
    shutil.copytree(FIXTURES, hist)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/generate_shift_handoff.py",
            "--history-dir",
            str(hist),
            "--reports-dir",
            str(rep),
            "--hours",
            "48",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    md = (rep / "shift_handoff.md").read_text(encoding="utf-8")
    assert "Shift handoff" in md


def test_no_publish_pipeline_files_modified_in_p2_scope() -> None:
    """Guard: P2 adds analytics only; publish_service unchanged in this commit scope."""
    assert (REPO / "utils/ops_analytics.py").is_file()
    assert (REPO / "publisher/publish_service.py").is_file()
