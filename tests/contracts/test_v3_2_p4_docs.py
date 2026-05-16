"""v3.2 P4 documentation and packaging contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/architecture/ADR-033-operational-packaging-and-maintenance.md",
    "docs/governance/operational_tooling_maintenance_policy.md",
    "docs/runbooks/offline_ops_recovery_drill.md",
    "docs/releases/v3_2_tooling_freeze.md",
)

TOOLS = (
    "tools/build_ops_release_kit.py",
    "tools/generate_ops_index.py",
    "utils/ops_release_kit.py",
    "utils/ops_index.py",
)

MAKEFILE_SNIPPETS = (
    "ops-release-validate",
    "build_ops_release_kit.py",
    "generate_ops_index.py",
)


@pytest.mark.parametrize("rel", DOCS + TOOLS)
def test_p4_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_makefile_ops_release_target() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    for snippet in MAKEFILE_SNIPPETS:
        assert snippet in text, snippet


def test_adr_forbids_platform_scope() -> None:
    text = (REPO / "docs/architecture/ADR-033-operational-packaging-and-maintenance.md").read_text(
        encoding="utf-8"
    )
    assert "Forbidden" in text
    assert "Hosted dashboards" in text or "hosted dashboards" in text.lower()
