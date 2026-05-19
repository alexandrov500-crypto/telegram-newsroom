from __future__ import annotations

import re
from urllib.parse import urlparse

from bot.config import get_high_trust_sources

SOURCE_TYPE_RSS = "rss"
SOURCE_TYPE_TELEGRAM = "telegram"
SOURCE_TYPE_UNKNOWN = "unknown"

TRUST_MIN = 0.05
TRUST_MAX = 0.99
DEFAULT_TRUST = 0.5
TELEGRAM_DEFAULT_TRUST = 0.55
HIGH_TRUST_INITIAL = 0.85
LOW_TRUST_INITIAL = 0.20

_SPAM_HINTS = frozenset({"sponsor", "promo", "advert", "affiliate", "giveaway"})


def clamp_trust(score: float) -> float:
    return max(TRUST_MIN, min(TRUST_MAX, score))


def normalize_source_name(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    text = str(raw).strip()
    if not text:
        return "unknown"
    if len(text) > 200:
        text = text[:200]
    if text.startswith("telegram:"):
        return text.lower()
    if text.startswith("http://") or text.startswith("https://"):
        host = urlparse(text).netloc.lower().removeprefix("www.")
        return host or text.lower()
    return text.lower()


def detect_source_type(source_name: str) -> str:
    name = source_name.lower()
    if name.startswith("telegram:"):
        return SOURCE_TYPE_TELEGRAM
    if "." in name and not name.startswith("@"):
        return SOURCE_TYPE_RSS
    if name.startswith("@"):
        return SOURCE_TYPE_TELEGRAM
    return SOURCE_TYPE_UNKNOWN


def initial_trust_score(source_name: str, source_type: str) -> float:
    lower = source_name.lower()
    if any(hint in lower for hint in _SPAM_HINTS):
        return LOW_TRUST_INITIAL

    high_trust = get_high_trust_sources()
    for trusted in high_trust:
        if trusted in lower:
            return HIGH_TRUST_INITIAL

    if any(
        token in lower
        for token in ("reuters", "bloomberg", "apnews", "associated press", "bbc.co")
    ):
        return HIGH_TRUST_INITIAL

    if source_type == SOURCE_TYPE_TELEGRAM:
        return TELEGRAM_DEFAULT_TRUST
    return DEFAULT_TRUST


def approval_ratio(*, accepted_count: int, rejected_count: int) -> float:
    total = accepted_count + rejected_count
    if total <= 0:
        return 0.5
    return accepted_count / total


def priority_trust_adjustment(
    *,
    trust_score: float,
    approval_ratio_value: float,
) -> tuple[float, str | None]:
    """
    Map trust + approval history into a priority delta.
    Returns (delta, reason_fragment).
    """
    trust_delta = (trust_score - DEFAULT_TRUST) * 0.24
    history_delta = (approval_ratio_value - 0.5) * 0.14
    total = trust_delta + history_delta
    if total > 0.06:
        return total, "trusted source"
    if total < -0.06:
        return total, "low-trust source"
    if abs(total) > 0.01:
        return total, "source reputation"
    return 0.0, None
