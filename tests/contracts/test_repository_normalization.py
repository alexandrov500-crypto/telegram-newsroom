"""Repository normalization checks (v3.2 FINAL)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = (
    "docs/START_HERE.md",
    "docs/architecture/README.md",
    "docs/architecture/ADR-030-v3-2-operational-tooling-scope.md",
    "docs/architecture/ADR-031-operational-analytics-layer.md",
    "docs/architecture/ADR-032-operational-schema-governance.md",
    "docs/architecture/ADR-033-operational-packaging-and-maintenance.md",
    "docs/architecture/ADR-034-v3-2-finalization-and-stewardship.md",
    "docs/governance/long_term_stewardship.md",
    "docs/governance/operational_tooling_maintenance_policy.md",
    "docs/repository/repository_normalization_report.md",
    "docs/releases/v3_2_final_manifest.md",
    "docs/releases/v3_2_stewardship_handoff.md",
    "docs/releases/offline_recovery_certification.md",
    "docs/releases/operational_maturity_assessment.md",
    "docs/runbooks/offline_ops_recovery_drill.md",
    "tools/build_ops_release_kit.py",
    "tools/generate_ops_index.py",
    "utils/ops_release_kit.py",
    "Makefile",
    ".gitignore",
)

OPS_TOOLS = (
    "tools/ops_metrics_snapshot.py",
    "tools/queue_introspection.py",
    "tools/publish_timeline_report.py",
    "tools/ops_analytics_aggregate.py",
    "tools/ops_visualize.py",
    "tools/ops_archive.py",
    "tools/generate_shift_handoff.py",
    "tools/validate_ops_schema.py",
    "tools/export_ops_bundle.py",
    "tools/generate_ops_html_report.py",
    "tools/build_ops_release_kit.py",
    "tools/generate_ops_index.py",
)

GITIGNORE_VAR_OPS = (
    "var/ops_history/",
    "var/ops_reports/",
    "var/ops_archive/",
    "var/ops_bundle/",
    "var/ops_release_kit/",
    "var/stewardship_audit/",
    "var/stewardship_integrity/",
    "var/immutable_archive/",
)

MAKEFILE_TARGETS = (
    "ops-tooling-validate",
    "ops-analytics-validate",
    "ops-bundle-validate",
    "ops-release-validate",
    "stewardship-validate",
    "stewardship-audit-validate",
    "immutable-baseline-validate",
    "archival-freeze-validate",
)


@pytest.mark.parametrize("rel", REQUIRED_PATHS + OPS_TOOLS)
def test_required_paths_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_gitignore_var_ops_entries() -> None:
    text = (REPO / ".gitignore").read_text(encoding="utf-8")
    for entry in GITIGNORE_VAR_OPS:
        assert entry in text, entry


def test_makefile_ops_targets() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in MAKEFILE_TARGETS:
        assert f"{target}:" in text, target


def test_start_here_v3_2_final_links() -> None:
    text = (REPO / "docs/START_HERE.md").read_text(encoding="utf-8")
    assert "stewardship-validate" in text
    assert "stewardship-audit-validate" in text
    assert "ADR-034" in text
    assert "stewardship_state_declaration" in text
    assert "archival-freeze-validate" in text
    assert "repository_terminal_state" in text
    assert "MAINTAINERS_GUIDE" in text


def test_architecture_index_adr_034() -> None:
    text = (REPO / "docs/architecture/README.md").read_text(encoding="utf-8")
    assert "ADR-034" in text


def test_readme_v3_2_ops_section() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "v3.2" in text
    assert "stewardship-validate" in text


def test_no_stale_ops_frozen_tag_only_in_policy() -> None:
    """Handoff uses v3.2-operational-tooling-freeze as canonical tag name."""
    handoff = (REPO / "docs/releases/v3_2_stewardship_handoff.md").read_text(encoding="utf-8")
    assert "v3.2-operational-tooling-freeze" in handoff


def test_start_here_markdown_links_resolve() -> None:
    text = (REPO / "docs/START_HERE.md").read_text(encoding="utf-8")
    base = REPO / "docs"
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        href = match.group(1).split("#")[0]
        if not href or href.startswith("http") or href.startswith("#"):
            continue
        target = (base / href).resolve()
        assert target.is_file() or target.is_dir(), f"broken link: {href}"
