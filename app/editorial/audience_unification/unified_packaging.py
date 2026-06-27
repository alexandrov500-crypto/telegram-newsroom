"""Unified attention packaging — Event → Interpretation → Implication → Takeaway."""

from __future__ import annotations

import re
from typing import Any

_CROSS_LINK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(ставк|fed|cpi|inflation|инфляц)", re.I), "Связь с рынками: ставки и ликвидность."),
    (re.compile(r"(ai|openai|nvidia|tech|нейросет)", re.I), "Связь с технологиями: сектор AI и инфраструктура."),
    (re.compile(r"(sanction|санкци|war|войн|nato|геополит)", re.I), "Связь с геополитикой: риски цепочек поставок."),
    (re.compile(r"(company|ipo|earnings|компан|бизнес)", re.I), "Связь с бизнесом: корпоративные решения и capex."),
]


def _infer_cross_domain_link(text: str) -> str:
    for pattern, link in _CROSS_LINK_PATTERNS:
        if pattern.search(text or ""):
            return link
    return "Связь с макроэкономикой: событие влияет на глобальный контекст решений."


def apply_unified_packaging(
    body: str,
    *,
    flagship: bool = False,
    existing_hashtags: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        if news_channel_beat_enabled():
            return (body or "").strip(), {"structure_applied": False, "skipped": "wire_beat"}
    except Exception:
        pass
    text = (body or "").strip()
    meta: dict[str, Any] = {"structure_applied": False, "layers": {}}
    if not text:
        return text, meta

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    headline = lines[0] if lines else ""
    meta["layers"]["headline"] = headline[:120]

    has_context = bool(re.search(r"(что\s+происходит|контекст|what\s+is\s+happening|факт)", text, re.I))
    has_implication = bool(re.search(r"(важн|значит|implication|почему|что\s+дальше)", text, re.I))
    has_cross = bool(re.search(r"(связь\s+с|cross|markets|geopolit|технолог)", text, re.I))

    out = text
    additions: list[str] = []

    if not has_context and len(lines) >= 1:
        additions.append("Что происходит: ключевое изменение фиксируется несколькими источниками.")
    if not has_implication:
        additions.append("Почему важно: это влияет на решения инвесторов, компаний и политиков.")
    if not has_cross:
        additions.append(_infer_cross_domain_link(text))

    if additions:
        out = f"{text}\n\n" + "\n".join(additions)
        meta["structure_applied"] = True
        meta["layers"]["context"] = additions[0] if additions else ""

    tags = list(existing_hashtags or [])[:2]
    if flagship and "#MustRead" not in tags and len(tags) < 2:
        tags.append("#MustRead")
        out = f"{out.rstrip()}\n\n#MustRead"
        meta["flagship_tag"] = True

    meta["hashtag_count"] = len(re.findall(r"#\w+", out))
    return out.strip(), meta
