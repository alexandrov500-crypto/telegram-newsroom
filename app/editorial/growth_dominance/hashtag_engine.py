"""Hashtag Growth Engine — attention clusters, not navigation."""

from __future__ import annotations

import re
from typing import Any

_MACRO_SHIFT = re.compile(r"(ставк|fed|fomc|inflation|cpi|gdp|бюджет|фискал|macro\s+shift)", re.I)
_AI_IMPACT = re.compile(r"(\bai\b|openai|nvidia|gpt|claude|gemini|нейросет|модел)", re.I)
_MARKET_SHOCK = re.compile(r"(crash|обвал|rally|record|surge|panic|moex|s&p|nasdaq|нефт.*\+|нефт.*\-)", re.I)
_GEO_TENSION = re.compile(r"(sanction|санкци|war|войн|nato|missile|дипломат|переговор.*сорван)", re.I)
_TECH_BREAK = re.compile(r"(launch|релиз|breakthrough|chip|semiconductor|quantum|прорыв)", re.I)

_GROWTH_CLUSTERS: list[tuple[re.Pattern[str], str]] = [
    (_MARKET_SHOCK, "#MarketShock"),
    (_AI_IMPACT, "#AIImpact"),
    (_MACRO_SHIFT, "#MacroShift"),
    (_GEO_TENSION, "#GeoTension"),
    (_TECH_BREAK, "#TechBreak"),
]

_RUBRIC_FALLBACK = {
    "market": "#MarketShock",
    "macro": "#MacroShift",
    "breaking": "#MarketShock",
    "geopolitics": "#GeoTension",
    "tech": "#TechBreak",
    "ai": "#AIImpact",
    "business": "#MacroShift",
    "digest": "#MacroShift",
    "context": "#MacroShift",
    "explainer": "#MacroShift",
}


def infer_growth_hashtag(
    text: str,
    *,
    editorial_category: str = "",
    post_type: str = "",
    dominance_loop: str = "",
) -> str:
    t = text or ""
    for pattern, tag in _GROWTH_CLUSTERS:
        if pattern.search(t):
            return tag
    cat = (editorial_category or post_type or "").lower()
    if cat in _RUBRIC_FALLBACK:
        return _RUBRIC_FALLBACK[cat]
    if dominance_loop == "awareness":
        return "#MarketShock"
    if dominance_loop == "retention":
        return "#MacroShift"
    return "#MacroShift"


def apply_growth_hashtags(
    body: str,
    *,
    editorial_category: str = "",
    post_type: str = "",
    dominance_loop: str = "",
    secondary_rubric: str | None = None,
) -> tuple[str, dict[str, Any]]:
    text = (body or "").strip()
    meta: dict[str, Any] = {"primary_cluster": "", "secondary": None, "applied": False}
    if not text:
        return text, meta
    try:
        from app.editorial.clean_channel_copy import clean_channel_copy_enabled

        if clean_channel_copy_enabled():
            return text, meta
    except Exception:
        pass

    primary = infer_growth_hashtag(
        text,
        editorial_category=editorial_category,
        post_type=post_type,
        dominance_loop=dominance_loop,
    )
    meta["primary_cluster"] = primary

    existing = re.findall(r"#[\w\u0400-\u04FF]+", text)
    growth_tags = {tag for _, tag in _GROWTH_CLUSTERS}
    kept = [h for h in existing if h in growth_tags][:2]

    out = text
    tags_to_add: list[str] = []
    if primary not in kept and primary not in existing:
        tags_to_add.append(primary)
    if secondary_rubric and secondary_rubric not in existing and len(tags_to_add) + len(kept) < 2:
        tags_to_add.append(secondary_rubric)
        meta["secondary"] = secondary_rubric

    if tags_to_add:
        out = f"{text}\n\n{' '.join(tags_to_add[:2])}"
        meta["applied"] = True

    return out.strip(), meta
