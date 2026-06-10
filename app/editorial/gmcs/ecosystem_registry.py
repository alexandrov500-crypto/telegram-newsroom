"""Telegram ecosystem competitor archetypes — not literal channel handles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CompetitorArchetype(str, Enum):
    MACRO_WIRE = "macro_wire"
    GEO_BREAKING = "geo_breaking"
    CRYPTO_SIGNAL = "crypto_signal"
    MARKET_ALERT = "market_alert"
    AI_DISRUPTION = "ai_disruption"
    LOCAL_CITY = "local_city"
    BUSINESS_EARNINGS = "business_earnings"
    OPINION_DIGEST = "opinion_digest"
    AGGREGATOR_RU = "aggregator_ru"
    PREMIUM_ANALYSIS = "premium_analysis"


@dataclass(frozen=True)
class EcosystemCompetitor:
    archetype: CompetitorArchetype
    label: str
    typical_subscribers: int
    publish_frequency_per_day: float
    strength_topics: tuple[str, ...]
    weakness: str
    substitution_vulnerability: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "archetype": self.archetype.value,
            "label": self.label,
            "typical_subscribers": self.typical_subscribers,
            "publish_frequency_per_day": self.publish_frequency_per_day,
            "strength_topics": list(self.strength_topics),
            "weakness": self.weakness,
            "substitution_vulnerability": round(self.substitution_vulnerability, 2),
        }


ECOSYSTEM_COMPETITORS: tuple[EcosystemCompetitor, ...] = (
    EcosystemCompetitor(
        CompetitorArchetype.MACRO_WIRE,
        "Macro wire channels",
        120_000,
        8.0,
        ("macro", "markets"),
        "no synthesis across domains",
        0.82,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.GEO_BREAKING,
        "Geo breaking feeds",
        95_000,
        12.0,
        ("geopolitics",),
        "noise without implication",
        0.78,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.CRYPTO_SIGNAL,
        "Crypto signal channels",
        80_000,
        15.0,
        ("crypto",),
        "hype cycles, low trust",
        0.75,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.MARKET_ALERT,
        "Market alert bots",
        60_000,
        20.0,
        ("markets",),
        "no context layer",
        0.80,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.AI_DISRUPTION,
        "AI disruption niche",
        45_000,
        6.0,
        ("ai", "tech"),
        "narrow vertical only",
        0.70,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.LOCAL_CITY,
        "Local city news",
        35_000,
        10.0,
        ("local",),
        "no global macro link",
        0.65,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.BUSINESS_EARNINGS,
        "Business / earnings",
        55_000,
        5.0,
        ("business",),
        "slow on breaking",
        0.68,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.AGGREGATOR_RU,
        "RU macro aggregators",
        150_000,
        25.0,
        ("macro", "geopolitics"),
        "duplicate streams, overload",
        0.88,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.OPINION_DIGEST,
        "Opinion / commentary",
        40_000,
        4.0,
        ("macro", "geopolitics"),
        "low signal density",
        0.55,
    ),
    EcosystemCompetitor(
        CompetitorArchetype.PREMIUM_ANALYSIS,
        "Premium analysis",
        25_000,
        2.0,
        ("macro", "markets", "ai"),
        "paywall friction",
        0.60,
    ),
)


def competitors_for_vertical(vertical: str) -> list[EcosystemCompetitor]:
    v = (vertical or "macro").lower()
    return [c for c in ECOSYSTEM_COMPETITORS if v in c.strength_topics or v == "macro"]
