"""v2.x preservation readiness contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PRESERVATION_DOCS = (
    "docs/preservation/ecosystem_aging.md",
    "docs/preservation/dependency_preservation.md",
    "docs/preservation/long_horizon_recovery.md",
    "docs/preservation/minimal_survivable_profile.md",
    "docs/preservation/operational_durability.md",
    "docs/preservation/preservation_governance.md",
    "docs/v2x_preservation_readiness_report.md",
)

REPORT_MARKERS = (
    "## Preservation Sustainability Grade",
    "## Remaining Long-Term Risks",
    "## Recommended Preservation Stewardship Model",
)


@pytest.mark.parametrize("rel", PRESERVATION_DOCS)
def test_preservation_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_preservation_report_sections() -> None:
    text = (REPO / "docs/v2x_preservation_readiness_report.md").read_text(encoding="utf-8")
    for m in REPORT_MARKERS:
        assert m in text


def test_no_vendor_directory() -> None:
    assert not (REPO / "vendor").is_dir()
    assert not (REPO / "third_party").is_dir()
