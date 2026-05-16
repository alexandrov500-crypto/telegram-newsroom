"""Toolchain reproducibility tests (v3.2 P3). Fixture-only, no network."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from utils.ops_bundle import build_ops_html_report, export_ops_bundle
from utils.ops_schema_governance import sha256_file, write_json_deterministic

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ops_history"
FROZEN = "2026-05-16T12:00:00Z"


@pytest.fixture(autouse=True)
def _frozen_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_FROZEN_UTC", FROZEN)


def test_double_export_identical_manifest(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundles"
    kwargs = dict(
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        bundle_root=bundle_root,
        limit=10,
    )
    a = export_ops_bundle(**kwargs)
    b = export_ops_bundle(**kwargs)
    man_a = json.loads((Path(a["bundle_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    man_b = json.loads((Path(b["bundle_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    assert man_a["files"] == man_b["files"]
    assert man_a["bundle_stamp"] == man_b["bundle_stamp"] == FROZEN.replace(":", "")


def test_checksums_match_manifest(tmp_path: Path) -> None:
    result = export_ops_bundle(
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        bundle_root=tmp_path / "bundles",
        limit=10,
    )
    bundle = Path(result["bundle_dir"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        assert sha256_file(bundle / entry["path"]) == entry["sha256"]


def test_html_report_deterministic(tmp_path: Path) -> None:
    result = export_ops_bundle(
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        bundle_root=tmp_path / "bundles",
        limit=10,
    )
    bundle = Path(result["bundle_dir"])
    validation = json.loads((bundle / "validation_report.json").read_text(encoding="utf-8"))
    h1 = build_ops_html_report(
        bundle_dir=bundle,
        validation_report=validation,
        analytics_path=bundle / "analytics_summary.json",
    )
    h2 = build_ops_html_report(
        bundle_dir=bundle,
        validation_report=validation,
        analytics_path=bundle / "analytics_summary.json",
    )
    assert h1 == h2
    assert "<!DOCTYPE html>" in h1
    assert "cdn" not in h1.lower()
    assert "<script" not in h1.lower()


def test_corruption_isolated_in_validation(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    hist.mkdir()
    for p in FIXTURES.glob("*.json"):
        (hist / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    (hist / "ops_metrics_corrupt.json").write_text("{", encoding="utf-8")
    result = export_ops_bundle(
        history_dir=hist,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        bundle_root=tmp_path / "bundles",
        limit=10,
    )
    validation = json.loads((Path(result["bundle_dir"]) / "validation_report.json").read_text(encoding="utf-8"))
    statuses = [r["status"] for r in validation.get("snapshots", [])]
    assert "CORRUPT" in statuses
    assert "OK" in statuses


def test_write_json_deterministic_stable(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    payload = {"b": 2, "a": 1}
    write_json_deterministic(path, payload)
    text = path.read_text(encoding="utf-8")
    assert text == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_frozen_env_used() -> None:
    assert os.environ.get("OPS_FROZEN_UTC") == FROZEN
