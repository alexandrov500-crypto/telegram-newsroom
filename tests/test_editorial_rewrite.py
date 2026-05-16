from __future__ import annotations

from ai.editorial_rewrite import rewrite_draft


def test_rewrite_short_truncates() -> None:
    body = "First paragraph only\n\nSecond paragraph"
    out = rewrite_draft(body, "short")
    assert "Second" not in out
    assert "First paragraph" in out


def test_rewrite_urgent_prefix() -> None:
    out = rewrite_draft("plain update", "urgent")
    assert out.upper().startswith("URGENT")


def test_rewrite_formal_prefix() -> None:
    out = rewrite_draft("Line one", "formal")
    assert "According to compiled sources" in out
