from __future__ import annotations

import json

from publisher.formatting import render_draft_preview, render_draft_preview_html


def test_render_draft_preview_basic() -> None:
    src = json.dumps([{"channel": "@a", "message_id": 1}, {"channel": "@b", "message_id": 2}])
    out = render_draft_preview(42, "Line1 title\n\nBody here.", src)
    assert "📰" in out
    assert "Line1 title" in out
    assert "Body here." in out
    assert "Источники:" in out
    assert "@a" in out or "a" in out
    assert "ID черновика: 42" in out


def test_render_draft_preview_missing_sources() -> None:
    out = render_draft_preview(1, "Only body", None)
    assert "Источники:" in out
    assert "ID черновика: 1" in out


def test_render_draft_preview_truncation() -> None:
    long_body = "x" * 5000
    out = render_draft_preview(3, long_body, "[]", max_chars=800)
    assert len(out) <= 800


def test_render_draft_preview_html_escapes() -> None:
    out = render_draft_preview_html(5, "<b>hi</b>", "not-json")
    assert "<pre>" in out
    assert "&lt;b&gt;hi&lt;/b&gt;" in out


def test_render_list_sources() -> None:
    items = [{"channel": "c1", "message_id": 9}]
    out = render_draft_preview(7, "t", items)
    assert "c1" in out
