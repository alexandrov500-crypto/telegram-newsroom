"""v1.4 release governance documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

GOVERNANCE_DOCS = (
    "docs/compatibility_policy.md",
    "docs/deprecation_policy.md",
    "docs/release_governance.md",
    "docs/migration_safety.md",
    "docs/evidence_lifecycle.md",
    "docs/feature_flag_governance.md",
    "docs/maintenance_matrix.md",
    "docs/v1_4_release_governance_report.md",
    "docs/architecture/ADR-020-release-governance-and-lifecycle.md",
)

UPGRADE_RUNBOOKS = (
    "docs/runbooks/upgrades/PATCH_UPGRADE.md",
    "docs/runbooks/upgrades/MINOR_UPGRADE.md",
    "docs/runbooks/upgrades/SAFE_ROLLBACK.md",
    "docs/runbooks/upgrades/EXPERIMENTAL_FLAG_ENABLE.md",
    "docs/runbooks/upgrades/SQLITE_MIGRATION_PRECHECK.md",
)


@pytest.mark.parametrize("rel", GOVERNANCE_DOCS)
def test_governance_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", UPGRADE_RUNBOOKS)
def test_upgrade_runbooks_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_compatibility_policy_sections() -> None:
    text = (REPO / "docs/compatibility_policy.md").read_text(encoding="utf-8")
    assert "Supported upgrade paths" in text or "Supported Upgrade Paths" in text
    assert "Freeze rules" in text or "Freeze Rules" in text
    assert "14" in text


def test_deprecation_zero_silent() -> None:
    text = (REPO / "docs/deprecation_policy.md").read_text(encoding="utf-8").lower()
    assert "silent" in text
    assert "zero" in text or "no silent" in text


def test_release_governance_classes() -> None:
    text = (REPO / "docs/release_governance.md").read_text(encoding="utf-8").lower()
    for word in ("patch", "minor", "operational", "experimental"):
        assert word in text


def test_release_readiness_tool_exists() -> None:
    assert (REPO / "tools/release_readiness.py").is_file()


def test_makefile_governance_target() -> None:
    assert "governance-validate" in (REPO / "Makefile").read_text(encoding="utf-8")
