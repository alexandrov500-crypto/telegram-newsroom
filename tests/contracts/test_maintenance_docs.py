"""Post-v1 maintenance documentation and template contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

MAINTENANCE_DOCS = (
    "docs/MAINTENANCE_MODE.md",
    "docs/ISSUE_TRIAGE.md",
    "docs/LTS_NOTES.md",
    "docs/DEPENDENCY_POLICY.md",
    "docs/architecture/ADR-018-post-v1-maintenance-mode.md",
)

ISSUE_TEMPLATES = (
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/documentation.md",
    ".github/ISSUE_TEMPLATE/operational-question.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
)

FORBIDDEN_GOVERNANCE_EXPANSION = (
    "new governance layer",
    "add a new runtime artifact",
    "orchestration engine",
    "kubernetes manifest",
    "prometheus",
    "grafana",
    "plugin system",
)

FREEZE_PHRASES = (
    "maintenance-first",
    "operationally frozen",
    "frozen",
)


@pytest.mark.parametrize("rel", MAINTENANCE_DOCS)
def test_maintenance_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", ISSUE_TEMPLATES)
def test_issue_templates_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_pr_template_exists() -> None:
    text = (REPO / ".github/pull_request_template.md").read_text(encoding="utf-8")
    assert "No runtime/governance contracts changed" in text
    assert "Runtime contract impact" in text


def test_maintenance_mode_statement() -> None:
    text = (REPO / "docs/MAINTENANCE_MODE.md").read_text(encoding="utf-8")
    assert "maintenance-first, not expansion-first" in text
    assert "architecture finalized" in text.lower() or "Architecture finalized" in text


def test_issue_triage_architecture_expansion_bar() -> None:
    text = (REPO / "docs/ISSUE_TRIAGE.md").read_text(encoding="utf-8")
    assert "architecture expansion" in text.lower()
    assert "exceptional justification" in text.lower()


def test_feature_request_template_justification_questions() -> None:
    text = (REPO / ".github/ISSUE_TEMPLATE/feature_request.md").read_text(encoding="utf-8")
    assert "existing operational model" in text.lower()
    assert "complexity increase" in text.lower()
    assert "solved externally" in text.lower()


def test_dependency_policy_complexity_statement() -> None:
    text = (REPO / "docs/DEPENDENCY_POLICY.md").read_text(encoding="utf-8")
    assert "Dependency count is treated as operational complexity" in text


def test_changelog_post_v1_maintenance_note() -> None:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Post-v1 maintenance" in text or "maintenance expectations" in text.lower()
    assert "frozen" in text.lower()


def test_freeze_wording_preserved_in_maturity_doc() -> None:
    text = (REPO / "docs/architecture/RUNTIME_MATURITY.md").read_text(encoding="utf-8")
    assert "operationally frozen as of v1.0.0" in text


def test_maintenance_docs_do_not_propose_governance_expansion() -> None:
    """Core maintenance policy docs should not advocate new governance subsystems."""
    for rel in ("docs/MAINTENANCE_MODE.md", "docs/DEPENDENCY_POLICY.md"):
        lower = (REPO / rel).read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_GOVERNANCE_EXPANSION:
            assert phrase not in lower, f"{rel} contains discouraged phrase: {phrase}"


def test_make_help_references_maintenance() -> None:
    import subprocess

    proc = subprocess.run(
        ["make", "-C", str(REPO), "help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "MAINTENANCE_MODE" in proc.stdout or "maintenance" in proc.stdout.lower()
    assert "release-check" in proc.stdout


def test_runtime_help_references_maintenance() -> None:
    import subprocess

    proc = subprocess.run(
        ["make", "-C", str(REPO), "runtime-help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "frozen" in proc.stdout.lower() or "MAINTENANCE" in proc.stdout
