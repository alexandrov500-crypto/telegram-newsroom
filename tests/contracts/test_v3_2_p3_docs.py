"""v3.2 P3 documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/architecture/ADR-032-operational-schema-governance.md",
    "docs/operations/operational_integrity_audit.md",
    "docs/releases/v3_2_p3_exit_criteria.md",
)

MAKEFILE_SNIPPETS = (
    "ops-bundle-validate",
    "validate_ops_schema.py",
    "export_ops_bundle.py",
    "generate_ops_html_report.py",
)


@pytest.mark.parametrize("rel", DOCS)
def test_p3_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_makefile_ops_bundle_target() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for snippet in MAKEFILE_SNIPPETS:
        assert snippet in makefile, snippet
