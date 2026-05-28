"""Reuters-style priority scoring for ingestion routing (deterministic, no ML)."""

from __future__ import annotations

import re
from enum import Enum

_BREAKING_KW = re.compile(
    r"\b(срочно|breaking|attack|war|sanctions|explosion|shutdown|urgent|"
    r"экстренно|взрыв|обстрел|resignation|default\s+alert)\b",
    re.I,
)
_HIGH_KW = re.compile(
    r"\b(росстат|инфляц|gdp|cpi|central\s+bank|фрс|fed\b|ecb|минюст|"
    r"geopolitic|regulat|sanction|тариф|ipo|earnings|sec\b|etf)\b",
    re.I,
)
_LOW_KW = re.compile(
    r"\b(мем|meme|lol|прикол|шутк|entertainment|giveaway|промокод|"
    r"подписывайтесь|to\s+the\s+moon)\b",
    re.I,
)
_FIN_SHOCK = re.compile(
    r"\b(emergency\s+rate|rate\s+hike|rate\s+cut|банкротств|default\s+on|"
    r"halt\s+trading|торги\s+приостановлен)\b",
    re.I,
)

# High-trust fast channels (Telegram handles vary: @DeCenter vs decenter).
_FAST_TRUST_CHANNELS = frozenset(
    {
        "@decenter",
        "decenter",
        "@vedomosti",
        "vedomosti",
        "@rbc_news",
        "rbc_news",
    }
)


class NewsPriority(str, Enum):
    BREAKING = "breaking"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


def _norm_source(item: dict) -> str:
    raw = str(item.get("source") or item.get("channel_name") or item.get("channel") or "")
    return raw.strip().lower()


def _text(item: dict) -> str:
    return str(item.get("text") or item.get("content") or "")


def score_news(item: dict) -> NewsPriority:
    """
    Classify a normalized ingest item into a priority lane.
    """
    text = _text(item)
    if not text.strip():
        return NewsPriority.LOW

    source = _norm_source(item)
    source_key = source if source.startswith("@") else f"@{source}" if source else ""

    if _LOW_KW.search(text) and not _BREAKING_KW.search(text):
        return NewsPriority.LOW

    if _BREAKING_KW.search(text) or _FIN_SHOCK.search(text):
        return NewsPriority.BREAKING

    if source_key in _FAST_TRUST_CHANNELS or source in _FAST_TRUST_CHANNELS:
        if _BREAKING_KW.search(text) or _FIN_SHOCK.search(text):
            return NewsPriority.BREAKING
        if len(text) > 120 and _HIGH_KW.search(text):
            return NewsPriority.HIGH

    if _HIGH_KW.search(text):
        return NewsPriority.HIGH

    if item.get("breaking_hint") or item.get("is_breaking"):
        return NewsPriority.BREAKING

    if len(text.strip()) < 50:
        return NewsPriority.LOW

    return NewsPriority.NORMAL
