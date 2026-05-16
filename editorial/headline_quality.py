"""Headline quality heuristics (no model calls)."""

from __future__ import annotations

import re
from typing import Any


def evaluate_headline_quality(headline: str, *, body_excerpt: str = "") -> dict[str, Any]:
    h = (headline or "").strip()
    warnings: list[str] = []
    score = 0.78
    if not h:
        return {"score": 0.0, "warnings": ["empty"]}
    if len(h) < 12:
        warnings.append("very_short")
        score -= 0.12
    if re.search(r"!{2,}", h):
        warnings.append("exclamation_spam")
        score -= 0.08
    if sum(1 for c in h if c.isupper()) > max(8, len(h) // 2):
        warnings.append("heavy_caps")
        score -= 0.1
    clickbait = re.compile(r"\b(you won't believe|shocking|secret|miracle|guaranteed)\b", re.I)
    if clickbait.search(h):
        warnings.append("clickbait_phrase")
        score -= 0.15
    words = re.findall(r"\w+", h.lower())
    if len(set(words)) <= 2 and len(words) >= 4:
        warnings.append("repetitive_tokens")
        score -= 0.1
    if body_excerpt and h.lower() in body_excerpt.lower()[:400]:
        score += 0.04
    else:
        if body_excerpt:
            warnings.append("weak_alignment_with_body")
            score -= 0.05
    if len(h) > 180:
        warnings.append("very_long")
        score -= 0.06
    score = max(0.0, min(1.0, score))
    return {"score": round(score, 4), "warnings": warnings}
