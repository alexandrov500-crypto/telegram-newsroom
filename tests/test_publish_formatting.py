from __future__ import annotations

import json

from publisher.publish_formatting import build_channel_message_html


def test_build_channel_html_no_sources_by_default() -> None:
    src = json.dumps([{"channel": "@c", "message_id": 5}])
    html = build_channel_message_html("Line one\n\n• bullet a\n• bullet b", src, draft_id=3)
    assert "Line one" in html
    assert "Sources" not in html
    assert "Draft #3" not in html


def test_build_channel_html_sources_when_enabled() -> None:
    src = json.dumps([{"channel": "@c", "message_id": 5}])
    html = build_channel_message_html(
        "Line one",
        src,
        draft_id=3,
        include_sources=True,
        include_draft_id_footer=True,
    )
    assert "Источник:" in html or "@c" in html
    assert "Sources" not in html
    assert "Draft #3" not in html
    assert "(5)" not in html


def test_truncation() -> None:
    long_body = "x" * 20000
    html = build_channel_message_html(long_body, "[]", draft_id=1, max_total_chars=500)
    assert len(html) <= 520
