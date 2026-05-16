from __future__ import annotations

import json

from publisher.formatting import render_rich_draft_preview_html


def test_preview_shows_priority_and_breaking() -> None:
    extras = json.dumps(
        {
            "priority": {
                "priority_level": "HIGH",
                "numeric_priority_score": 0.88,
                "moderation_hint": "Review soon.",
                "reasoning": "urgency=0.9",
            },
            "breaking": {"is_breaking": True, "breaking_score": 0.71, "reasoning": "urgency_keywords"},
            "title_suggestions": {"short_title": "S", "standard_title": "Std", "urgent_title": "URGENT: Std"},
            "rewrite_suggestions": {"short": "short body"},
            "category_confidence": 0.81,
            "category_reasoning": "matched keywords",
        }
    )
    html = render_rich_draft_preview_html(
        3,
        "body",
        "[]",
        draft_extras_json=extras,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )
    assert "Priority" in html
    assert "Breaking" in html
    assert "Title suggestions" in html
    assert "Rewrite" in html
    assert "Stale draft" in html
