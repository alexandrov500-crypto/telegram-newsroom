"""End-to-end offline ops toolchain (v3.2 P4). Fixture-only, no network."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from utils.ops_analytics import build_analytics_summary, build_visualization_bundle
from utils.ops_bundle import build_ops_html_report, export_ops_bundle
from utils.ops_index import build_ops_index_html
from utils.ops_release_kit import build_ops_release_kit, verify_release_kit_checksums
from utils.ops_schema_governance import build_schema_validation_report

FIXTURES = Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "ops_history"
FROZEN = "2026-05-16T12:00:00Z"


@pytest.fixture(autouse=True)
def _frozen_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_FROZEN_UTC", FROZEN)


def test_e2e_offline_toolchain(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    archive = tmp_path / "archive"
    bundle_root = tmp_path / "bundles"
    kit_root = tmp_path / "kits"
    reports.mkdir()
    archive.mkdir()

    summary = build_analytics_summary(FIXTURES, limit=10)
    assert summary["snapshot_count"] >= 1

    charts = build_visualization_bundle(summary)
    assert charts

    validation = build_schema_validation_report(
        history_dir=FIXTURES,
        reports_dir=reports,
        archive_dir=archive,
    )
    assert validation["status"] in ("OK", "WARNING")

    bundle = export_ops_bundle(
        history_dir=FIXTURES,
        reports_dir=reports,
        archive_dir=archive,
        bundle_root=bundle_root,
        limit=10,
    )
    bundle_dir = Path(bundle["bundle_dir"])
    assert (bundle_dir / "manifest.json").is_file()

    html = build_ops_html_report(
        bundle_dir=bundle_dir,
        validation_report=json.loads((bundle_dir / "validation_report.json").read_text(encoding="utf-8")),
        analytics_path=bundle_dir / "analytics_summary.json",
    )
    (reports / "operations_report.html").write_text(html, encoding="utf-8")

    kit = build_ops_release_kit(
        history_dir=FIXTURES,
        reports_dir=reports,
        archive_dir=archive,
        kit_root=kit_root,
        limit=10,
    )
    kit_dir = Path(kit["kit_dir"])
    assert (kit_dir / "VERSION").read_text(encoding="utf-8").strip()
    assert (kit_dir / "README.txt").is_file()
    assert (kit_dir / "operations_report.html").is_file()
    assert (kit_dir / "retention_status.json").is_file()

    ok, errors = verify_release_kit_checksums(kit_dir)
    assert ok, errors

    index_html = build_ops_index_html(
        reports_dir=reports,
        release_kit_root=kit_root,
        bundle_root=bundle_root,
    )
    assert "Operations index" in index_html
    assert "cdn" not in index_html.lower()

    man1 = json.loads((kit_dir / "manifest.json").read_text(encoding="utf-8"))
    kit2 = build_ops_release_kit(
        history_dir=FIXTURES,
        reports_dir=reports,
        archive_dir=archive,
        kit_root=kit_root,
        limit=10,
    )
    man2 = json.loads((Path(kit2["kit_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    assert man1["files"] == man2["files"]


def test_frozen_env_active() -> None:
    assert os.environ.get("OPS_FROZEN_UTC") == FROZEN
