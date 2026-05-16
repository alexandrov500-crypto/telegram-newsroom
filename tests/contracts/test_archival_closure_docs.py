"""Archival closure documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/releases/v3_2_archival_closure_report.md",
    "docs/releases/v3_2_publication_manifest.md",
    "docs/releases/v3_2_archival_freeze_tag.md",
    "docs/releases/repository_terminal_state.md",
    "docs/governance/final_repository_preservation_audit.md",
    "tools/build_archival_integrity_seal.py",
    "utils/archival_seal.py",
)


@pytest.mark.parametrize("rel", DOCS)
def test_archival_closure_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_makefile_archival_freeze_target() -> None:
    assert "archival-freeze-validate" in (REPO / "Makefile").read_text(encoding="utf-8")


def test_terminal_state_no_implicit_roadmap() -> None:
    text = (REPO / "docs/releases/repository_terminal_state.md").read_text(encoding="utf-8")
    assert "no implicit" in text.lower() or "No implicit" in text
