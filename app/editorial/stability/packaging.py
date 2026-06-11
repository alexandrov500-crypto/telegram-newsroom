"""Editorial packaging — rubric hashtags and structure hints."""

from __future__ import annotations

import re
from typing import Any

_RUBRIC_TAGS = {
    "markets": "#Рынки",
    "market": "#Рынки",
    "macro": "#Экономика",
    "economy": "#Экономика",
    "economics": "#Экономика",
    "tech": "#AI",
    "technology": "#AI",
    "ai": "#AI",
    "geopolitics": "#Геополитика",
    "geo": "#Геополитика",
    "business": "#Бизнес",
    "context": "#Контекст",
    "explainer": "#Контекст",
    "digest": "#Контекст",
}

_ALLOWED = frozenset(_RUBRIC_TAGS.values())

_MARKET_RE = re.compile(r"(рынок|бирж|акци|moex|nasdaq|s&p|нефт|oil|fx|курс)", re.I)
_ECON_RE = re.compile(r"(инфляц|ставк|цб|fed|gdp|бюджет|эконом)", re.I)
_AI_RE = re.compile(r"(\bai\b|openai|nvidia|искусственн\w*\s+интеллект|нейросет)", re.I)
_GEO_RE = re.compile(r"(санкци|войн|nato|геополит|дипломат|переговор)", re.I)
_BIZ_RE = re.compile(r"(компан|ipo|merger|corporate|бизнес|earnings)", re.I)


def infer_rubric_tag(text: str, *, editorial_category: str = "", post_type: str = "") -> str:
    cat = (editorial_category or post_type or "").strip().lower()
    if cat in _RUBRIC_TAGS:
        return _RUBRIC_TAGS[cat]
    if post_type in {"digest", "explainer", "context"}:
        return "#Контекст"
    t = text or ""
    if _AI_RE.search(t):
        return "#AI"
    if _GEO_RE.search(t):
        return "#Геополитика"
    if _MARKET_RE.search(t):
        return "#Рынки"
    if _ECON_RE.search(t):
        return "#Экономика"
    if _BIZ_RE.search(t):
        return "#Бизнес"
    return "#Контекст"


def apply_editorial_packaging(
    body: str,
    *,
    editorial_category: str = "",
    post_type: str = "",
    include_share_cta: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Ensure at most 1–2 rubric hashtags; optional forward CTA for digest/context.
    Does not rewrite body structure — adds footer lines if missing.
    """
    text = (body or "").strip()
    meta: dict[str, Any] = {"rubric_tag": "", "packaging_applied": False}
    if not text:
        return text, meta
    try:
        from app.editorial.clean_channel_copy import clean_channel_copy_enabled

        if clean_channel_copy_enabled():
            return text, meta
    except Exception:
        pass

    tag = infer_rubric_tag(text, editorial_category=editorial_category, post_type=post_type)
    meta["rubric_tag"] = tag

    existing = [m.group(0) for m in re.finditer(r"#[\w\u0400-\u04FF]+", text)]
    kept = [h for h in existing if h in _ALLOWED][:2]

    out = text
    if not kept:
        out = f"{text}\n\n{tag}"
        meta["packaging_applied"] = True
    elif tag not in kept and len(kept) < 2:
        out = f"{text}\n{tag}"
        meta["packaging_applied"] = True

    if include_share_cta and post_type in {"digest", "explainer", "context"}:
        cta = "Перешлите коллеге, если следите за темой."
        if cta.lower() not in out.lower():
            out = f"{out}\n\n{cta}"
            meta["share_cta"] = True

    return out.strip(), meta
