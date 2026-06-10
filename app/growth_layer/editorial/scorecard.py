"""Editorial scorecard for post analysis (does not affect routing/publish)."""

from __future__ import annotations

from typing import Any

from app.growth_layer.editorial.feature_extraction import extract_editorial_features
from app.growth_layer.editorial.pattern_discovery import discover_growth_patterns


def _clamp(v: float) -> int:
    return max(0, min(100, int(round(v))))


def _score_bool_alignment(post_val: bool, pattern: dict[str, Any]) -> float:
    lift = pattern.get("lift")
    if lift is None:
        return 50.0
    top = float(pattern.get("top") or 0)
    bottom = float(pattern.get("bottom") or 0)
    preferred = top >= bottom
    if preferred and post_val:
        return 50.0 + min(40.0, abs(float(lift)) / 2.0)
    if preferred and not post_val:
        return 50.0 - min(30.0, abs(float(lift)) / 3.0)
    if not preferred and not post_val:
        return 50.0 + min(40.0, abs(float(lift)) / 2.0)
    return 50.0 - min(30.0, abs(float(lift)) / 3.0)


def _score_numeric_alignment(value: float, pattern: dict[str, Any]) -> float:
    rng = pattern.get("top_range") or {}
    lo, hi = rng.get("low"), rng.get("high")
    if lo is None or hi is None:
        return 50.0
    if lo <= value <= hi:
        return 85.0
    span = max(float(hi) - float(lo), 1.0)
    dist = min(abs(value - float(lo)), abs(value - float(hi)))
    penalty = min(40.0, (dist / span) * 25.0)
    return max(10.0, 85.0 - penalty)


def evaluate_post_editorial_score(
    post: dict[str, Any],
    *,
    segment_discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Score post editorial quality vs segment winning patterns.
    Analysis-only — no routing or publish impact.
    """
    features = extract_editorial_features(post)
    segment = str(features.get("content_segment") or "general_news")
    if segment_discovery is None:
        segment_discovery = discover_growth_patterns([{**features, **post}], segment=segment)

    headline_scores: list[float] = []
    for feat in ("has_number", "has_percent", "has_question", "has_colon", "has_quote"):
        pat = (segment_discovery.get("patterns") or {}).get(feat) or {}
        headline_scores.append(_score_bool_alignment(bool(features.get(feat)), pat))
    headline_scores.append(
        _score_numeric_alignment(
            float(features.get("headline_word_count") or 0),
            (segment_discovery.get("numeric_patterns") or {}).get("headline_word_count") or {},
        )
    )
    headline_quality = sum(headline_scores) / len(headline_scores)

    structure_scores: list[float] = []
    for feat in ("paragraph_count", "link_count", "emoji_count", "body_length"):
        structure_scores.append(
            _score_numeric_alignment(
                float(features.get(feat) or 0),
                (segment_discovery.get("numeric_patterns") or {}).get(feat) or {},
            )
        )
    structure_quality = sum(structure_scores) / len(structure_scores)

    segment_alignment = (headline_quality + structure_quality) / 2.0
    score = headline_quality * 0.4 + structure_quality * 0.35 + segment_alignment * 0.25

    return {
        "score": _clamp(score),
        "headline_quality": _clamp(headline_quality),
        "structure_quality": _clamp(structure_quality),
        "segment_alignment": _clamp(segment_alignment),
        "content_segment": segment,
        "features": features,
    }
