"""v2.x historical traceability contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

STEWARDSHIP_DOCS = (
    "docs/stewardship/adr_lineage_map.md",
    "docs/stewardship/release_archaeology.md",
    "docs/stewardship/operational_history.md",
    "docs/stewardship/ecosystem_continuity.md",
    "docs/stewardship/decision_archaeology_index.md",
    "docs/stewardship/long_term_readability.md",
    "docs/v2x_historical_traceability_report.md",
)


@pytest.mark.parametrize("rel", STEWARDSHIP_DOCS)
def test_stewardship_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_history_guardrails_exists() -> None:
    assert (REPO / "tools/history_guardrails.py").is_file()


def test_report_sections() -> None:
    text = (REPO / "docs/v2x_historical_traceability_report.md").read_text(encoding="utf-8")
    for marker in (
        "## Historical Sustainability Grade",
        "## Remaining Historical Blind Spots",
        "## Recommended Stewardship Continuity Model",
    ):
        assert marker in text
