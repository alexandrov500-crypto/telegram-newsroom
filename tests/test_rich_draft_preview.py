from __future__ import annotations

import json

from publisher.formatting import render_rich_draft_preview_html


def test_rich_preview_contains_sections() -> None:
    extras = json.dumps(
        {
            "quality": {"coherence": 0.91, "repetition": 0.88},
            "tags": ["#AI", "#OpenAI"],
            "category": "tech",
        }
    )
    dup = {
        "severity": "medium",
        "max_similarity_pct": 87.5,
        "related": [{"draft_id": 9, "similarity_pct": 87.5}],
        "warning_lines": ["Check overlap"],
    }
    html = render_rich_draft_preview_html(
        42,
        "OpenAI launches new reasoning model\n\nShort summary here.",
        [{"channel": "@openai", "message_id": 1}, {"channel": "@technews", "message_id": 2}],
        editor_title="OpenAI launches new reasoning model",
        editor_summary="Short summary here.",
        draft_extras_json=extras,
        status="pending",
        created_at_iso="2026-05-12T12:00:00+00:00",
        scheduled_at_iso="2026-05-12T18:30:00+00:00",
        duplicate_intel=dup,
        publish_warnings=["Long post"],
    )
    assert "OpenAI" in html
    assert "связность" in html
    assert "Дубликаты" in html
    assert "@openai" in html or "openai" in html.lower()
    assert "Теги" in html
    assert "Запланирован" in html
    assert "ID черновика" in html
    assert "<code>42</code>" in html


def test_rich_preview_graceful_missing() -> None:
    html = render_rich_draft_preview_html(1, "", None, status="failed")
    assert "ID черновика" in html
