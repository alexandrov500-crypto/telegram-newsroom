"""v2.x legacy stewardship contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

LEGACY_DOCS = (
    "docs/legacy/legacy_state_definition.md",
    "docs/legacy/controlled_sunset.md",
    "docs/legacy/recoverability_guarantees.md",
    "docs/legacy/legacy_operational_envelope.md",
    "docs/legacy/stewardship_sunset_governance.md",
    "docs/legacy/legacy_antipatterns.md",
    "docs/v2x_legacy_stewardship_report.md",
)

REPORT_MARKERS = (
    "## Legacy Stewardship Grade",
    "## Recommended Final Stewardship Posture",
    "## Dormant-State Survivability",
)


@pytest.mark.parametrize("rel", LEGACY_DOCS)
def test_legacy_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_legacy_report_sections() -> None:
    text = (REPO / "docs/v2x_legacy_stewardship_report.md").read_text(encoding="utf-8")
    for m in REPORT_MARKERS:
        assert m in text


def test_no_shutdown_automation_tool() -> None:
    assert not (REPO / "tools" / "shutdown_project.py").is_file()
