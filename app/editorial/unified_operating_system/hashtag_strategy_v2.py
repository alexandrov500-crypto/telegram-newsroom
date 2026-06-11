"""Hashtag Strategy v2 — anti-fragmentation, navigation anchors."""

from __future__ import annotations

import re
from typing import Any

_PRIMARY_CLUSTERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(crash|обвал|surge|panic|moex|market\s+shock|нефт.*\+|record\s+high)", re.I), "#MarketShock"),
    (re.compile(r"(\bai\b|openai|nvidia|gpt|disruption|нейросет|llm)", re.I), "#AIDisruption"),
    (re.compile(r"(sanction|war|nato|геополит|missile|geo\s+shift|дипломат.*криз)", re.I), "#GeoShift"),
    (re.compile(r"(fed|fomc|cpi|gdp|macro|ставк|инфляц|бюджет)", re.I), "#MacroFlow"),
    (re.compile(r"(chip|semiconductor|tech\s+signal|startup|cloud|saas)", re.I), "#TechSignal"),
    (re.compile(r"(global|глобал|world\s+signal|cross.?domain|несколько\s+источник)", re.I), "#GlobalSignal"),
]

_CROSS_DOMAIN_SECONDARY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(crypto|btc|eth|биткоин)", re.I), "#MacroFlow"),
    (re.compile(r"(city|москв|local|регион)", re.I), "#GlobalSignal"),
]

_CATEGORY_PRIMARY = {
    "markets": "#MarketShock",
    "macro": "#MacroFlow",
    "geopolitics": "#GeoShift",
    "tech": "#TechSignal",
    "ai": "#AIDisruption",
    "crypto": "#MacroFlow",
    "breaking": "#MarketShock",
    "digest": "#GlobalSignal",
}


def infer_primary_hashtag(text: str, *, editorial_category: str = "") -> str:
    for pattern, tag in _PRIMARY_CLUSTERS:
        if pattern.search(text or ""):
            return tag
    cat = (editorial_category or "").lower()
    return _CATEGORY_PRIMARY.get(cat, "#GlobalSignal")


def infer_secondary_hashtag(text: str, primary: str) -> str | None:
    for pattern, tag in _CROSS_DOMAIN_SECONDARY:
        if tag != primary and pattern.search(text or ""):
            return tag
    return None


def apply_hashtag_strategy_v2(
    body: str,
    *,
    editorial_category: str = "",
    flagship: bool = False,
) -> tuple[str, dict[str, Any]]:
    text = (body or "").strip()
    meta: dict[str, Any] = {"primary": None, "secondary": None, "applied": False}
    if not text:
        return text, meta
    try:
        from app.editorial.clean_channel_copy import clean_channel_copy_enabled

        if clean_channel_copy_enabled():
            return text, meta
    except Exception:
        pass

    primary = infer_primary_hashtag(text, editorial_category=editorial_category)
    secondary = infer_secondary_hashtag(text, primary)

    stripped = re.sub(r"#\w+", "", text).strip()
    tags = [primary]
    if secondary:
        tags.append(secondary)
    if flagship and "#MustRead" not in tags and len(tags) < 2:
        tags.append("#MustRead")

    out = f"{stripped}\n\n" + " ".join(tags[:2])
    meta.update({"primary": primary, "secondary": secondary, "applied": True, "tag_count": len(tags[:2])})
    return out.strip(), meta
