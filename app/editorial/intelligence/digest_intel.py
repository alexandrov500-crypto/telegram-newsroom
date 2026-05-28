"""Digest intelligence — theme grouping hints (advisory)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


def digest_theme_hints(texts: list[str]) -> dict[str, Any]:
    """Group cluster texts into coarse themes for digest briefing."""
    buckets: Counter[str] = Counter()
    patterns = [
        ("markets", re.compile(r"(market|бирж|crypto|btc|fed|ставк)", re.I)),
        ("politics", re.compile(r"(president|parliament|выбор|sanction|санкц)", re.I)),
        ("tech", re.compile(r"(ai|openai|apple|google|tech|стартап)", re.I)),
        ("culture", re.compile(r"(film|music|art|культур|кино)", re.I)),
    ]
    for t in texts:
        matched = False
        for name, rx in patterns:
            if rx.search(t or ""):
                buckets[name] += 1
                matched = True
                break
        if not matched:
            buckets["general"] += 1
    dominant = buckets.most_common(1)[0][0] if buckets else "general"
    return {
        "theme_counts": dict(buckets),
        "dominant_theme": dominant,
        "signal_vs_noise": "signal" if buckets[dominant] >= max(2, len(texts) // 2) else "mixed",
    }
