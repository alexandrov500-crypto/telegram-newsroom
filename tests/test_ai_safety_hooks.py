from __future__ import annotations

from ai.safety_hooks import scan_draft_output


def test_safety_empty() -> None:
    assert "empty_body" in scan_draft_output("")


def test_safety_repetition() -> None:
    w = scan_draft_output("foo " * 40)
    assert "excessive_repetition" in w or "low_lexical_diversity" in w
