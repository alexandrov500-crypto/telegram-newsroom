"""Stewardship doc linkage and chronology."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_release_archaeology_covers_freeze() -> None:
    text = (REPO / "docs/stewardship/release_archaeology.md").read_text(encoding="utf-8")
    assert "v1.0" in text.lower()
    assert "semantics" in text.lower()


def test_decision_index_links_phases() -> None:
    text = (REPO / "docs/stewardship/decision_archaeology_index.md").read_text(encoding="utf-8")
    assert "020" in text
    assert "RFC-005" in text
    assert "Rejected" in text


def test_adr_lineage_preserves_non_goals() -> None:
    text = (REPO / "docs/stewardship/adr_lineage_map.md").read_text(encoding="utf-8")
    assert "Kubernetes" in text or "kubernetes" in text.lower()
    assert "non-goals" in text.lower() or "Non-goals" in text


def test_operational_history_bounded() -> None:
    text = (REPO / "docs/stewardship/operational_history.md").read_text(encoding="utf-8")
    assert "NOT be preserved" in text or "should NOT" in text
