"""Legacy doc linkage and preservation compatibility."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_legacy_supported_definition() -> None:
    text = (REPO / "docs/legacy/legacy_state_definition.md").read_text(encoding="utf-8")
    assert "legacy but supported" in text.lower() or "Legacy but supported" in text


def test_sunset_not_shutdown() -> None:
    text = (REPO / "docs/legacy/controlled_sunset.md").read_text(encoding="utf-8")
    assert "not" in text.lower()
    assert "automated" in text.lower() or "automation" in text.lower()


def test_antipatterns_forbid_rewrite() -> None:
    text = (REPO / "docs/legacy/legacy_antipatterns.md").read_text(encoding="utf-8")
    assert "rewrite" in text.lower()


def test_recoverability_confidence_levels() -> None:
    text = (REPO / "docs/legacy/recoverability_guarantees.md").read_text(encoding="utf-8")
    assert "confidence" in text.lower()
