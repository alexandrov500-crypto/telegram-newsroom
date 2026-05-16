"""v3.2 FINAL documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

FINAL_DOCS = (
    "docs/architecture/ADR-034-v3-2-finalization-and-stewardship.md",
    "docs/governance/long_term_stewardship.md",
    "docs/repository/repository_normalization_report.md",
    "docs/releases/offline_recovery_certification.md",
    "docs/releases/operational_maturity_assessment.md",
    "docs/releases/v3_2_final_manifest.md",
    "docs/releases/v3_2_stewardship_handoff.md",
)


@pytest.mark.parametrize("rel", FINAL_DOCS)
def test_final_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_adr_034_forbids_platform_expansion() -> None:
    text = (REPO / "docs/architecture/ADR-034-v3-2-finalization-and-stewardship.md").read_text(encoding="utf-8")
    assert "Forbidden" in text
    assert "Platformization" in text or "platformization" in text


def test_stewardship_when_not_to_build() -> None:
    text = (REPO / "docs/governance/long_term_stewardship.md").read_text(encoding="utf-8")
    assert "when NOT to build more tooling" in text.lower() or "When NOT to build" in text


def test_manifest_lists_all_adrs() -> None:
    text = (REPO / "docs/releases/v3_2_final_manifest.md").read_text(encoding="utf-8")
    for n in range(30, 35):
        assert f"ADR-0{n}" in text
