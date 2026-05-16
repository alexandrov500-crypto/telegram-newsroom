"""Schema governance contracts (v3.2 P3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.ops_analytics import ANALYTICS_SCHEMA_VERSION
from utils.ops_schema_governance import (
    DIAGNOSTICS_SCHEMA_VERSION,
    VALIDATION_REPORT_SCHEMA_VERSION,
    build_schema_validation_report,
    validate_snapshot_file,
)
from utils.ops_tooling import OPS_SNAPSHOT_SCHEMA_VERSION

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "tools" / "fixtures" / "ops_history"


def test_version_constants_documented() -> None:
    assert OPS_SNAPSHOT_SCHEMA_VERSION == 1
    assert DIAGNOSTICS_SCHEMA_VERSION == 2
    assert ANALYTICS_SCHEMA_VERSION == 1
    assert VALIDATION_REPORT_SCHEMA_VERSION == 1


def test_fixture_snapshots_validate_ok() -> None:
    for path in sorted(FIXTURES.glob("*.json")):
        row = validate_snapshot_file(path)
        assert row["status"] in ("OK", "WARN"), row


def test_validation_report_shape(tmp_path: Path) -> None:
    report = build_schema_validation_report(
        history_dir=FIXTURES,
        reports_dir=tmp_path,
        archive_dir=tmp_path / "arch",
    )
    assert report["schema_version"] == VALIDATION_REPORT_SCHEMA_VERSION
    assert report["read_only"] is True
    assert report["offline"] is True
    assert "governance" in report
    assert report["counts"]["snapshots"] >= 1


def test_corrupt_snapshot_marked(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    row = validate_snapshot_file(bad)
    assert row["status"] == "CORRUPT"


@pytest.mark.parametrize(
    "rel",
    (
        "docs/architecture/ADR-032-operational-schema-governance.md",
        "docs/operations/operational_integrity_audit.md",
        "docs/releases/v3_2_p3_exit_criteria.md",
        "tools/validate_ops_schema.py",
        "tools/export_ops_bundle.py",
        "tools/generate_ops_html_report.py",
        "utils/ops_schema_governance.py",
        "utils/ops_bundle.py",
    ),
)
def test_p3_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_adr_forbids_runtime_coupling() -> None:
    text = (REPO / "docs/architecture/ADR-032-operational-schema-governance.md").read_text(encoding="utf-8")
    assert "Forbidden" in text
    assert "runtime" in text.lower()
    assert "No changes to production-lite runtime" in text or "No changes to production" in text


def test_validation_report_json_deterministic_keys(tmp_path: Path) -> None:
    report = build_schema_validation_report(
        history_dir=FIXTURES,
        reports_dir=tmp_path,
        archive_dir=tmp_path,
    )
    raw = json.dumps(report, indent=2, sort_keys=True)
    again = json.dumps(report, indent=2, sort_keys=True)
    assert raw == again
