"""Maps typical 10–20 channel subscriptions → hub vertical coverage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Archetypal channels a overloaded Telegram user might follow (not literal handles).
_SUBSTITUTION_TARGETS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(macro|fed|cpi|gdp|ставк|инфляц|central\s+bank|econom)", re.I), "macro", "macro_wire_channels"),
    (re.compile(r"(market|moex|s&p|nasdaq|обвал|surge|trading|акци)", re.I), "markets", "market_signal_channels"),
    (re.compile(r"(war|svo|сво|nato|sanction|geo|геополит|missile|conflict)", re.I), "geopolitics", "geo_breaking_channels"),
    (re.compile(r"(btc|eth|crypto|биткоин|blockchain|defi)", re.I), "crypto", "crypto_signal_channels"),
    (re.compile(r"(city|город|local|регион|municipal|transit)", re.I), "local", "local_city_channels"),
    (re.compile(r"(openai|nvidia|gpt|ai\b|нейросет|llm|tech)", re.I), "ai", "ai_disruption_channels"),
    (re.compile(r"(oil|gas|energy|нефт|opec|power\s+grid)", re.I), "energy", "energy_channels"),
    (re.compile(r"(earnings|corporate|ipo|merger|бизнес|company)", re.I), "business", "business_channels"),
    (re.compile(r"(canada|ottawa|toronto|vancouver|канад)", re.I), "geopolitics", "diaspora_news_channels"),
    (re.compile(r"(science|research|breakthrough|наук)", re.I), "science", "science_trend_channels"),
]


@dataclass(frozen=True)
class HubSubstitutionResult:
    vertical: str
    channels_replaced_estimate: int
    matched_archetypes: tuple[str, ...]
    substitution_score: float
    hub_value_proposition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertical": self.vertical,
            "channels_replaced_estimate": self.channels_replaced_estimate,
            "matched_archetypes": list(self.matched_archetypes),
            "substitution_score": round(self.substitution_score, 2),
            "hub_value_proposition": self.hub_value_proposition,
        }


def infer_vertical(text: str, editorial_category: str = "") -> str:
    for pattern, vertical, _ in _SUBSTITUTION_TARGETS:
        if pattern.search(text or ""):
            return vertical
    cat = (editorial_category or "").lower()
    if cat in {"macro", "markets", "geopolitics", "ai", "crypto", "local", "business", "energy", "science"}:
        return cat
    return "macro"


def evaluate_hub_substitution(
    text: str,
    *,
    editorial_category: str = "",
    cluster_size: int = 1,
) -> HubSubstitutionResult:
    t = text or ""
    matched: list[str] = []
    verticals: set[str] = set()

    for pattern, vertical, archetype in _SUBSTITUTION_TARGETS:
        if pattern.search(t):
            matched.append(archetype)
            verticals.add(vertical)

    primary = infer_vertical(t, editorial_category)
    if not verticals:
        verticals.add(primary)

    # Cross-domain posts replace more external channels.
    base_replace = min(12, 2 + len(verticals) * 2 + max(0, cluster_size - 1))
    score = 45.0 + len(verticals) * 12.0 + min(20.0, cluster_size * 4.0)
    if len(verticals) >= 3:
        score += 15.0
    score = min(100.0, score)

    vprop = (
        f"Один пост закрывает {base_replace}+ типичных каналов: "
        + ", ".join(sorted(verticals)[:4])
    )

    return HubSubstitutionResult(
        vertical=primary,
        channels_replaced_estimate=base_replace,
        matched_archetypes=tuple(matched[:6]),
        substitution_score=score,
        hub_value_proposition=vprop,
    )
