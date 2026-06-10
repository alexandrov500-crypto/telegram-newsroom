"""Analyze draft content for growth-relevant editorial features."""

from __future__ import annotations

import json
from typing import Any

from app.growth_layer.editorial.feature_extraction import draft_to_post_dict, extract_editorial_features
from app.growth_layer.segments.content_segments import classify_content_segment


def _draft_to_dict(draft: Any) -> dict[str, Any]:
    if isinstance(draft, dict):
        return draft
    return {
        "draft_id": getattr(draft, "id", None),
        "content": getattr(draft, "content", "") or "",
        "sources": getattr(draft, "sources", "[]") or "[]",
        "draft_extras": getattr(draft, "draft_extras", None),
        "editor_title": getattr(draft, "editor_title", None),
        "editor_summary": getattr(draft, "editor_summary", None),
    }


def _parse_extras(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def analyze_draft_growth_potential(draft: Any) -> dict[str, Any]:
    """
    Extract growth-relevant editorial features from a draft.
    Reuses Phase 2C feature extraction — no duplicated logic.
    """
    data = _draft_to_dict(draft)
    extras = _parse_extras(data.get("draft_extras"))
    growth = extras.get("growth") if isinstance(extras.get("growth"), dict) else {}
    topic_bucket = str(extras.get("category") or extras.get("topic_bucket") or "")
    segment = str(data.get("content_segment") or "") or classify_content_segment(
        {"draft_extras": data.get("draft_extras"), "topic_bucket": topic_bucket, "category": topic_bucket}
    )
    post = draft_to_post_dict(
        draft_id=int(data.get("draft_id") or 0),
        content=str(data.get("content") or ""),
        sources=str(data.get("sources") or "[]"),
        draft_extras=data.get("draft_extras") if isinstance(data.get("draft_extras"), str) else json.dumps(extras),
        editor_title=data.get("editor_title"),
        editor_summary=data.get("editor_summary"),
        content_segment=segment,
        format_profile=str(growth.get("format_profile") or extras.get("format_profile") or ""),
        virality_tier=str(growth.get("virality_tier") or extras.get("virality_tier") or ""),
    )
    features = extract_editorial_features(post)
    return {
        "draft_id": int(data.get("draft_id") or 0),
        "content_segment": segment,
        "format_profile": str(features.get("format_profile") or "cb_brief"),
        "virality_tier": str(features.get("virality_tier") or "standard"),
        "headline_length": features.get("headline_length"),
        "headline_word_count": features.get("headline_word_count"),
        "has_number": features.get("has_number"),
        "has_percent": features.get("has_percent"),
        "has_currency": features.get("has_currency"),
        "has_question": features.get("has_question"),
        "has_colon": features.get("has_colon"),
        "has_quote": features.get("has_quote"),
        "uppercase_ratio": features.get("uppercase_ratio"),
        "body_length": features.get("body_length"),
        "paragraph_count": features.get("paragraph_count"),
        "bullet_count": features.get("bullet_count"),
        "emoji_count": features.get("emoji_count"),
        "link_count": features.get("link_count"),
        "source_count": features.get("source_count"),
        "features": features,
        "post": post,
    }
