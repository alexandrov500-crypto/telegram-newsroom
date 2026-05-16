"""Immutable baseline documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/architecture/ADR-036-immutable-stewardship-certification.md",
    "docs/releases/immutable_repository_certification.md",
    "docs/releases/stewardship_preservation_declaration.md",
    "docs/governance/governance_preservation_audit.md",
)

TOOLS = (
    "tools/build_repository_fingerprint.py",
    "tools/build_immutable_archive_bundle.py",
    "utils/repository_fingerprint.py",
    "utils/immutable_archive.py",
)


@pytest.mark.parametrize("rel", DOCS + TOOLS)
def test_immutable_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_makefile_immutable_target() -> None:
    assert "immutable-baseline-validate" in (REPO / "Makefile").read_text(encoding="utf-8")


def test_adr_036_forbids_platformization() -> None:
    text = (REPO / "docs/architecture/ADR-036-immutable-stewardship-certification.md").read_text(encoding="utf-8")
    assert "Forbidden" in text
    assert "platformization" in text.lower()
