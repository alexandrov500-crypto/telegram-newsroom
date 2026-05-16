from __future__ import annotations

from editorial.diffing import format_edit_history, headline_and_lead_diff, unified_text_diff


def test_unified_text_diff() -> None:
    d = unified_text_diff("a\nb", "a\nc", label_a="x", label_b="y")
    assert "a" in d and "c" in d


def test_headline_and_lead_diff() -> None:
    r = headline_and_lead_diff(
        draft_content="Auto line one\npara",
        editor_title="Different",
        editor_summary="para",
    )
    assert "title_diff" in r and "summary_diff" in r


def test_format_edit_history() -> None:
    raw = '[{"ts":"t","action":"edit_title","value":"Hi"}]'
    txt = format_edit_history(raw)
    assert "edit_title" in txt
