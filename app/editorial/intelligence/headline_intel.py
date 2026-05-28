"""Headline intelligence — anti-clickbait, anti-generic."""

from __future__ import annotations

import re
from typing import Any

from editorial.headline_quality import evaluate_headline_quality

_GENERIC = re.compile(
    r"^(important|breaking|update|news|новости|важно|срочно|latest)\b",
    re.I,
)


def evaluate_headline_intelligence(
    headline: str,
    *,
    body_excerpt: str = "",
    recent_headlines: list[str] | None = None,
) -> dict[str, Any]:
    base = evaluate_headline_quality(headline, body_excerpt=body_excerpt)
    warnings = list(base.get("warnings") or [])
    score = float(base.get("score") or 0.0)
    h = (headline or "").strip()
    if _GENERIC.match(h):
        warnings.append("generic_opener")
        score -= 0.1
    for prev in (recent_headlines or [])[:10]:
        if not prev:
            continue
        if h.lower()[:40] == str(prev).lower()[:40]:
            warnings.append("headline_pattern_repeat")
            score -= 0.15
            break
    score = max(0.0, min(1.0, score))
    return {"score": round(score, 4), "warnings": warnings}
