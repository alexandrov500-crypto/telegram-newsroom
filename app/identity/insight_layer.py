"""Insight extraction — why-it-matters layer (rule-based, no LLM required)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IMPLICATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(rate\s+cut|rate\s+hike|ключев.*ставк|повыш.*ставк|сниз.*ставк)", re.I),
     "Изменение ставки перестраивает стоимость капитала и волатильность активов."),
    (re.compile(r"\b(sanction|санкц)", re.I),
     "Санкционный контур меняет логистику поставок и ценовые премии на риск."),
    (re.compile(r"\b(oil|нефт|OPEC|gas|газ)", re.I),
     "Энергетический шок быстро передаётся в инфляцию и транспортные издержки."),
    (re.compile(r"\b(BTC|Bitcoin|ETH|crypto|крипт)", re.I),
     "Крипторынок реагирует на ликвидность и регуляторные сигналы быстрее традиционных активов."),
    (re.compile(r"\b(Putin|Trump|NATO|войн|war|conflict)", re.I),
     "Геополитический риск повышает премию за защитные активы и усложняет торговые маршруты."),
    (re.compile(r"\b(earnings|revenue|profit|выручк|прибыл)", re.I),
     "Корпоративные результаты задают тон секторным мультипликаторам и ожиданиям по guidance."),
    (re.compile(r"\b(default|bankruptcy|дефолт|банкрот)", re.I),
     "Кредитное событие перераспределяет риск между кредиторами и контрагентами."),
]


@dataclass(frozen=True)
class InsightResult:
    text: str
    depth_score: float
    has_insight: bool
    rule_id: str


def extract_insight(body: str, *, vertical: str = "general") -> InsightResult:
    """Append implication sentence if missing."""
    t = " ".join((body or "").split()).strip()
    if not t:
        return InsightResult("", 0.0, False, "empty")

    has_marker = any(
        m in t
        for m in (
            "Почему это важно",
            "Это означает",
            "Следствие",
            "Контекст:",
            "для рынков",
            "влияет на",
            "риск для",
        )
    )
    if has_marker:
        return InsightResult(t, 0.82, True, "existing")

    insight = ""
    rule_id = "none"
    for pat, sentence in _IMPLICATION_RULES:
        if pat.search(t):
            insight = sentence
            rule_id = pat.pattern[:32]
            break

    if not insight:
        # No keyword-matched implication — do not invent a generic market line.
        return InsightResult(t, 0.35, False, "none")

    enriched = f"{t}\n\nПочему это важно: {insight}"
    return InsightResult(enriched, 0.65, True, rule_id)


def score_insight_depth(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    score = 0.35
    if "Почему это важно" in t or "Это означает" in t:
        score += 0.25
    if len(t) >= 280:
        score += 0.1
    sents = len(re.findall(r"[.!?]", t))
    if sents >= 3:
        score += 0.15
    for pat, _ in _IMPLICATION_RULES:
        if pat.search(t):
            score += 0.15
            break
    return round(min(1.0, score), 4)
