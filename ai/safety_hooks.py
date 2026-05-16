"""Lightweight output heuristics (no external moderation API)."""

from __future__ import annotations

import re
from collections import Counter


def scan_draft_output(text: str, *, headline: str = "") -> list[str]:
    """Return human-readable warning codes for suspicious model output."""
    warns: list[str] = []
    t = (text or "").strip()
    if not t:
        warns.append("empty_body")
        return warns
    if len(t) < 40:
        warns.append("very_short_body")
    words = re.findall(r"\w+", t.lower())
    if len(words) >= 12:
        top = Counter(words).most_common(1)[0]
        if top[1] >= max(6, len(words) // 4):
            warns.append("excessive_repetition")
    uniq_ratio = len(set(words)) / max(1, len(words))
    if len(words) > 30 and uniq_ratio < 0.25:
        warns.append("low_lexical_diversity")
    if re.search(r"<script|javascript:|onerror\s*=", t, re.IGNORECASE):
        warns.append("suspicious_html")
    if headline and len(headline) > 220:
        warns.append("headline_too_long")
    return warns
