"""v2.x operational semantics contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SEMANTICS_DOCS = (
    "docs/semantics/operational_invariants.md",
    "docs/semantics/forbidden_states.md",
    "docs/semantics/recovery_semantics.md",
    "docs/semantics/consistency_matrix.md",
    "docs/semantics/assumption_audit.md",
    "docs/semantics/semantics_governance.md",
    "docs/v2x_operational_semantics_report.md",
)

RECOVERY_MARKERS = (
    "## What recovery guarantees exist",
    "## What recovery guarantees DO NOT exist",
)


@pytest.mark.parametrize("rel", SEMANTICS_DOCS)
def test_semantics_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_recovery_semantics_sections() -> None:
    text = (REPO / "docs/semantics/recovery_semantics.md").read_text(encoding="utf-8")
    for m in RECOVERY_MARKERS:
        assert m in text


def test_consistency_matrix_table() -> None:
    text = (REPO / "docs/semantics/consistency_matrix.md").read_text(encoding="utf-8")
    assert "| Component | Consistency model |" in text
    assert "SQLite" in text


def test_no_runtime_semantics_package() -> None:
    assert not (REPO / "semantics_engine").is_dir()
