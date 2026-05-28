from __future__ import annotations

import json

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.scoring_engine import score_story
from publisher.public_renderer import (
    clean_headline,
    format_source_footer,
    render_internal_review_html,
    render_public_post,
    render_public_post_html,
)
from publisher.publish_formatting import build_channel_message_html


_DEBUG_BODY = """\
Quality: 0.82
Duplicates: 2 similar
Priority: high

Apple удалила более 1200 приложений из российского App Store.

Источник: @old_leak
"""

_SOURCES = json.dumps([{"channel": "@cb_economics", "message_id": 99}])


def test_public_post_has_no_debug_sections() -> None:
    plain = render_public_post(_DEBUG_BODY, _SOURCES)
    html = render_public_post_html(_DEBUG_BODY, _SOURCES)
    for blob in (plain, html):
        assert "Quality" not in blob
        assert "Duplicates" not in blob
        assert "Priority" not in blob
        assert "message_id" not in blob
        assert "99" not in blob or "1200" in blob
    assert "Apple" in plain
    assert "cb_economics" in plain


def test_source_footer_rendered() -> None:
    assert format_source_footer("@cb_economics") == "Источник: @cb_economics"
    html = render_public_post_html("Заголовок\n\nКраткое summary.", _SOURCES)
    assert "Источник:" in html
    assert "@cb_economics" in html
    assert "\n\n" in html


def test_internal_render_preserves_diagnostics() -> None:
    extras = json.dumps({"quality_score": 0.91, "priority": "high"})
    html = render_internal_review_html(
        7,
        _DEBUG_BODY,
        _SOURCES,
        draft_extras_json=extras,
        status="pending",
    )
    assert "Quality" in html or "quality" in html.lower()
    assert "Draft" in html or "#7" in html or "7" in html


def test_clean_headline_generation() -> None:
    raw = "[@spam] [@spam] Apple удалила приложения https://example.com/x"
    assert clean_headline(raw).startswith("Apple")
    assert "http" not in clean_headline(raw)
    assert "[@spam]" not in clean_headline(raw)
    long = "Слово " * 80
    assert len(clean_headline(long, max_len=60)) <= 62


def test_public_render_markdown_safe() -> None:
    body = "<script>alert(1)</script>\n\nТекст & «цитата»"
    html = render_public_post_html(body, "[]")
    assert "<script>" not in html
    assert "&lt;" in html or "alert" not in html


def test_adult_topic_rejected() -> None:
    text = (
        "Аналитики обсуждают экономику секс-работы и рост спроса на эскорт-услуги "
        "в крупных городах как отдельный рынок."
    )
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@decenter"])
    assert not desk.publish
    assert desk.reason == "unsafe_public_topic"


def test_build_channel_uses_public_footer_not_message_ids() -> None:
    html = build_channel_message_html(
        "Заголовок\n\nТело новости.",
        _SOURCES,
        draft_id=3,
        include_sources=True,
        include_draft_id_footer=True,
    )
    assert "Источник:" in html or "via @" in html
    assert "Sources" not in html
    assert "Draft #3" not in html
    assert "(99)" not in html
