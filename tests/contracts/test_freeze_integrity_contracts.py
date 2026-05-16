"""Freeze integrity and stewardship audit contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.freeze_integrity import (
    FREEZE_TAG,
    INTEGRITY_REPORT_SCHEMA_VERSION,
    build_freeze_integrity_report,
)
from utils.stewardship_audit import build_stewardship_audit_bundle, default_stewardship_audit_root

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "tools" / "fixtures" / "ops_history"
FROZEN = "2026-05-16T12:00:00Z"


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_FROZEN_UTC", FROZEN)


@pytest.mark.parametrize(
    "rel",
    (
        "tools/check_freeze_integrity.py",
        "tools/build_stewardship_audit_bundle.py",
        "utils/freeze_integrity.py",
        "utils/stewardship_audit.py",
        "docs/governance/stewardship_operations_calendar.md",
        "docs/governance/drift_detection_policy.md",
        "docs/governance/maintenance_branch_policy.md",
        "docs/runbooks/maintenance_hotfix_procedure.md",
        "docs/releases/stewardship_state_declaration.md",
    ),
)
def test_stewardship_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_freeze_integrity_report_shape() -> None:
    report = build_freeze_integrity_report(REPO)
    assert report["schema_version"] == INTEGRITY_REPORT_SCHEMA_VERSION
    assert report["freeze_tag"] == FREEZE_TAG
    assert report["status"] in ("OK", "WARNING", "FAIL")
    assert len(report.get("checks") or []) >= 4


def test_forbidden_path_not_present() -> None:
    report = build_freeze_integrity_report(REPO)
    check = next(c for c in report["checks"] if c["id"] == "forbidden_paths_absent")
    assert check["status"] == "OK"


def test_stewardship_audit_bundle_bounded(tmp_path: Path) -> None:
    result = build_stewardship_audit_bundle(
        repo_root=REPO,
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        audit_root=tmp_path / "audit",
    )
    audit_dir = Path(result["audit_dir"])
    assert (audit_dir / "freeze_integrity_report.json").is_file()
    assert (audit_dir / "manifest.json").is_file()
    assert result["freeze_integrity_status"] in ("OK", "WARNING")


def test_drift_policy_covers_coupling() -> None:
    text = (REPO / "docs/governance/drift_detection_policy.md").read_text(encoding="utf-8")
    assert "runtime/tooling coupling" in text.lower() or "Runtime/tooling" in text


def test_makefile_stewardship_audit_target() -> None:
    assert "stewardship-audit-validate" in (REPO / "Makefile").read_text(encoding="utf-8")
