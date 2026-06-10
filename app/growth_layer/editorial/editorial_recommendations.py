"""Generate human-readable editorial recommendations from discovered patterns."""

from __future__ import annotations

from typing import Any

from app.growth_layer.editorial.pattern_discovery import (
    BOOLEAN_FEATURES,
    NUMERIC_FEATURES,
    discover_all_segment_patterns,
)

_LIFT_THRESHOLD = 25.0
_NUMERIC_LIFT_THRESHOLD = 15.0

_BOOL_LABELS: dict[str, tuple[str, str]] = {
    "has_number": ("Use numeric headlines", "Avoid relying on numbers in headlines"),
    "has_percent": ("Include percentages when relevant", "Reduce percentage-heavy headlines"),
    "has_currency": ("Currency figures can boost engagement", "Avoid currency-heavy headlines"),
    "has_question": ("Question headlines can work in this segment", "Avoid question headlines"),
    "has_colon": ("Colon-style headlines perform well", "Prefer single-clause headlines over colon splits"),
    "has_quote": ("Quoted headlines correlate with success", "Avoid long quotations in headlines"),
}

_NUMERIC_LABELS: dict[str, str] = {
    "headline_word_count": "headline word count",
    "headline_length": "headline length",
    "paragraph_count": "paragraph count",
    "link_count": "link count",
    "emoji_count": "emoji count",
    "body_length": "body length",
    "bullet_count": "bullet count",
    "source_count": "source count",
}


def _format_range(rng: dict[str, Any]) -> str:
    lo, hi = rng.get("low"), rng.get("high")
    if lo is None or hi is None:
        return ""
    if lo == hi:
        return str(lo)
    return f"{lo}–{hi}"


def _recommendations_from_discovery(discovery: dict[str, Any]) -> tuple[list[str], list[str]]:
    winning: list[str] = []
    avoid: list[str] = []

    for feat in BOOLEAN_FEATURES:
        block = (discovery.get("patterns") or {}).get(feat) or {}
        lift = block.get("lift")
        if lift is None:
            continue
        pos, neg = _BOOL_LABELS.get(feat, (feat, feat))
        if lift >= _LIFT_THRESHOLD:
            winning.append(pos)
        elif lift <= -_LIFT_THRESHOLD:
            avoid.append(neg)

    for feat in NUMERIC_FEATURES:
        block = (discovery.get("numeric_patterns") or {}).get(feat) or {}
        lift = block.get("lift")
        label = _NUMERIC_LABELS.get(feat, feat.replace("_", " "))
        top_range = block.get("top_range") or {}
        rng = _format_range(top_range)
        if lift is not None and lift >= _NUMERIC_LIFT_THRESHOLD and rng:
            winning.append(f"Prefer {label} around {rng}")
        elif lift is not None and lift <= -_NUMERIC_LIFT_THRESHOLD and rng:
            avoid.append(f"Top posts use lower {label} (winning range {rng})")

    return winning[:6], avoid[:6]


def generate_editorial_recommendations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build segment-specific winning patterns and anti-patterns."""
    discoveries = discover_all_segment_patterns(rows)
    out: dict[str, Any] = {}
    for segment, discovery in discoveries.items():
        winning, anti = _recommendations_from_discovery(discovery)
        out[segment] = {
            "winning_patterns": winning,
            "anti_patterns": anti,
            "discovery": discovery,
        }
    return out


def recommendations_as_bullets(segment_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    return list(segment_data.get("winning_patterns") or []), list(segment_data.get("anti_patterns") or [])
