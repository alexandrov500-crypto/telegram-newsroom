"""Headline intelligence upgrade — entity-first, consequence-driven, forward-optimized."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_FORBIDDEN = re.compile(
    r"(шок|сенсаци|вы не повер|срочно смотр|100%|гарантир|"
    r"you won'?t believe|shocking|must see|click here)",
    re.I,
)
_ENTITY = re.compile(
    r"\b(Fed|ECB|BOJ|OPEC|BTC|ETH|Apple|Tesla|Putin|Trump|Xi|"
    r"ЦБ|ФРС|ЕЦБ|Путин|нефть|Bitcoin)\b",
    re.I,
)
_CONSEQUENCE = re.compile(
    r"\b(raises?|cuts?|sanctions?|default|surge|drop|halt|ban|approve|"
    r"повыш|сниз|санкц|дефолт|рост|паден|запрет|одобр)\b",
    re.I,
)
_TEMPLATES: dict[str, str] = {
    "macro": "{entity}: {action} → {impact}",
    "crypto": "{entity} {move} as {driver}",
    "geopolitics": "{entity} {action} — {consequence}",
    "energy": "{entity}: {supply_move} hits {market}",
    "finance": "{entity} {corporate_action} ({size})",
}


@dataclass(frozen=True)
class HeadlineCandidate:
    text: str
    score: float
    variant: str
    warnings: tuple[str, ...]


def _clamp_score(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)


def score_headline(headline: str, *, vertical: str = "macro", body_excerpt: str = "") -> float:
    h = (headline or "").strip()
    if not h or len(h) < 12:
        return 0.0
    score = 0.45
    if _FORBIDDEN.search(h):
        return 0.05
    if _ENTITY.search(h):
        score += 0.22
    if _CONSEQUENCE.search(h):
        score += 0.18
    if "→" in h or "—" in h or ":" in h:
        score += 0.08
    if len(h) <= 120:
        score += 0.07
    try:
        from app.editorial.intelligence.headline_intel import evaluate_headline_intelligence

        intel = evaluate_headline_intelligence(h, body_excerpt=body_excerpt)
        score = score * 0.6 + float(intel.get("score") or 0.0) * 0.4
    except Exception:
        pass
    return _clamp_score(score)


def generate_headline_variants(
    body: str,
    *,
    vertical: str = "macro",
    entity_hint: str = "",
) -> list[HeadlineCandidate]:
    """Rule-based variants before optional LLM rewrite."""
    text = " ".join((body or "").split())
    if not text:
        return []
    first_sent = text.split(".", 1)[0].strip()
    entity = entity_hint or (_ENTITY.search(text).group(0) if _ENTITY.search(text) else "")
    variants: list[HeadlineCandidate] = []

    def add(v: str, variant: str) -> None:
        s = score_headline(v, vertical=vertical, body_excerpt=text[:400])
        warnings: list[str] = []
        if _FORBIDDEN.search(v):
            warnings.append("forbidden_pattern")
        variants.append(HeadlineCandidate(v[:200], s, variant, tuple(warnings)))

    add(first_sent[:180], "lead_sentence")
    if entity:
        tpl = _TEMPLATES.get(vertical, _TEMPLATES["macro"])
        add(tpl.format(entity=entity, action="update", impact="markets", move="", driver="", consequence="", supply_move="", market="", corporate_action="", size=""), "template")
        add(f"{entity}: {first_sent[:120]}", "entity_first")
    ranked = sorted(variants, key=lambda c: c.score, reverse=True)
    return ranked


def pick_best_headline(body: str, *, vertical: str = "macro", entity_hint: str = "") -> str:
    cands = generate_headline_variants(body, vertical=vertical, entity_hint=entity_hint)
    if not cands:
        return body.split(".", 1)[0].strip()[:200]
    best = cands[0]
    if best.score < 0.55:
        return body.split(".", 1)[0].strip()[:200]
    return best.text


def apply_headline_to_content(content: str, headline: str) -> str:
    """Prepend entity-first headline if content doesn't already lead with it."""
    h = (headline or "").strip()
    c = (content or "").strip()
    if not h or c.lower().startswith(h.lower()[:40]):
        return c
    return f"{h}\n\n{c}"
