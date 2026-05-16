"""Preservation doc linkage and coverage."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_long_horizon_scenarios() -> None:
    text = (REPO / "docs/preservation/long_horizon_recovery.md").read_text(encoding="utf-8")
    assert "5 years" in text.lower()
    assert "maintainer gap" in text.lower()


def test_minimal_profile_not_feature_minimum() -> None:
    text = (REPO / "docs/preservation/minimal_survivable_profile.md").read_text(encoding="utf-8")
    assert "recoverable" in text.lower()
    assert "not minimum feature" in text.lower() or "not minimum feature set" in text.lower()


def test_dependency_critical_tier() -> None:
    text = (REPO / "docs/preservation/dependency_preservation.md").read_text(encoding="utf-8")
    assert "telethon" in text.lower()
    assert "do not aggressively modernize" in text.lower()


def test_links_stewardship() -> None:
    text = (REPO / "docs/preservation/preservation_governance.md").read_text(encoding="utf-8")
    assert "traceability" in text.lower() or "stewardship" in text.lower()
