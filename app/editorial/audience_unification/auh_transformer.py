"""AUH Transformer — news item → decision-relevant unified signal."""

from __future__ import annotations

import re
from typing import Any

_JARGON = re.compile(
    r"\b(spread|basis\s+points|b\.p\.|liquidity|gamma\s+squeeze|fomc\s+dot\s+plot)\b",
    re.I,
)
_NICHE_ONLY = re.compile(
    r"(только\s+для\s+подписчиков|premium\s+канал|закрытый\s+канал|продолжение\s+в\s+)",
    re.I,
)
_CROSS_DOMAIN_HINTS = {
    "macro_economy": "Это влияет на ставки, инфляцию и корпоративные решения.",
    "markets": "Рынки уже закладывают это в цены активов.",
    "geopolitics": "Геополитический контекст усиливает неопределённость для бизнеса.",
    "ai_tech": "Технологический сектор реагирует быстрее традиционных отраслей.",
    "business": "Компании пересматривают стратегии и инвестиционные планы.",
}


def _add_global_context(body: str, matched_interests: tuple[str, ...]) -> str:
    if re.search(r"(глобальн|worldwide|international|для\s+миров)", body, re.I):
        return body
    if matched_interests:
        hint = _CROSS_DOMAIN_HINTS.get(matched_interests[0], "")
        if hint and hint not in body:
            return f"{body.rstrip()}\n\n{hint}"
    return body


def _explain_jargon(body: str) -> str:
    out = body
    if _JARGON.search(out) and "б.п." not in out.lower() and "basis point" not in out.lower():
        if re.search(r"\bb\.p\.|\bbasis\s+points\b", out, re.I):
            out += "\n(б.п. — базисные пункты, 0,01 п.п.)"
    return out


def transform_for_unified_audience(
    body: str,
    *,
    matched_interests: tuple[str, ...] = (),
    editorial_category: str = "",
) -> tuple[str, dict[str, Any]]:
    text = (body or "").strip()
    meta: dict[str, Any] = {"transformed": False, "rules_applied": []}
    try:
        from app.editorial.clean_channel_copy import clean_channel_copy_enabled

        if clean_channel_copy_enabled():
            return text, meta
    except Exception:
        pass
    if not text or _NICHE_ONLY.search(text):
        return text, meta

    out = text
    if _JARGON.search(out):
        out = _explain_jargon(out)
        meta["rules_applied"].append("jargon_explained")
        meta["transformed"] = True

    if not re.search(r"(важн|значит|matters|implication|почему)", out, re.I):
        out += "\n\nПочему это важно: событие влияет на решения инвесторов, бизнеса и политики."
        meta["rules_applied"].append("implicit_global_context")
        meta["transformed"] = True

    if not re.search(r"(дальше|следующ|expect|ожида|что\s+дальше)", out, re.I):
        out += "\n\nЧто дальше: следим за подтверждением и реакцией рынков."
        meta["rules_applied"].append("implication_layer")
        meta["transformed"] = True

    enriched = _add_global_context(out, matched_interests or (editorial_category,))
    if enriched != out:
        out = enriched
        meta["rules_applied"].append("cross_domain_link")
        meta["transformed"] = True

    return out.strip(), meta
