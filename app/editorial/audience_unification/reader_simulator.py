"""Composite unified reader persona — not niche segments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_INTEREST_PATTERNS: dict[str, re.Pattern[str]] = {
    "macro_economy": re.compile(r"(инфляц|ставк|gdp|cpi|fed|цб|бюджет|macro|эконом)", re.I),
    "ai_tech": re.compile(r"(\bai\b|openai|nvidia|tech|нейросет|gpt|chip|semiconductor)", re.I),
    "geopolitics": re.compile(r"(санкци|войн|nato|геополит|дипломат|переговор|sanction)", re.I),
    "markets": re.compile(r"(рынок|бирж|акци|moex|nasdaq|fx|нефт|oil|bond|yield)", re.I),
    "business": re.compile(r"(компан|ipo|merger|corporate|earnings|бизнес|retail)", re.I),
    "energy": re.compile(r"(нефт|газ|opec|energy|энерг|электр)", re.I),
    "science": re.compile(r"(наук|research|space|nasa|clinical|arxiv)", re.I),
}


@dataclass(frozen=True)
class UnifiedReaderProfile:
    interests: dict[str, float] = field(
        default_factory=lambda: {
            "macro_economy": 0.8,
            "ai_tech": 0.85,
            "geopolitics": 0.75,
            "markets": 0.9,
            "business": 0.7,
            "energy": 0.6,
            "science": 0.5,
        }
    )
    prefers_explainers: bool = True
    prefers_context_over_news: bool = True
    hates_noise: bool = True
    attention_span: str = "medium_high"
    save_time: bool = True
    avoid_multiple_channels: bool = True
    decision_support: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "interests": dict(self.interests),
            "cognitive_style": {
                "prefers_explainers": self.prefers_explainers,
                "prefers_context_over_news": self.prefers_context_over_news,
                "hates_noise": self.hates_noise,
                "attention_span": self.attention_span,
            },
            "motivation": {
                "save_time": self.save_time,
                "avoid_multiple_channels": self.avoid_multiple_channels,
                "decision_support": self.decision_support,
            },
        }


def default_reader_profile() -> UnifiedReaderProfile:
    return UnifiedReaderProfile()


def _interest_hits(text: str) -> dict[str, float]:
    hits: dict[str, float] = {}
    for key, pattern in _INTEREST_PATTERNS.items():
        if pattern.search(text or ""):
            hits[key] = 1.0
    return hits


@dataclass(frozen=True)
class ReaderSimulationResult:
    reader_relevance_score: float
    reader_unification_score: float
    gender_neutral_clarity_score: float
    matched_interests: tuple[str, ...]
    cross_interest_breadth: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "reader_relevance_score": round(self.reader_relevance_score, 2),
            "reader_unification_score": round(self.reader_unification_score, 2),
            "gender_neutral_clarity_score": round(self.gender_neutral_clarity_score, 2),
            "matched_interests": list(self.matched_interests),
            "cross_interest_breadth": self.cross_interest_breadth,
        }


def evaluate_reader_profile(
    text: str,
    *,
    profile: UnifiedReaderProfile | None = None,
) -> ReaderSimulationResult:
    p = profile or default_reader_profile()
    t = text or ""
    hits = _interest_hits(t)
    breadth = len(hits)

    relevance = 35.0
    for key, weight in p.interests.items():
        if key in hits:
            relevance += weight * 12.0
    relevance = min(100.0, relevance)

    unification = 30.0 + breadth * 12.0
    if breadth >= 3:
        unification += 15.0
    if p.prefers_context_over_news and re.search(r"(важн|значит|implication|почему|контекст)", t, re.I):
        unification += 10.0
    unification = min(100.0, unification)

    clarity = 50.0
    if len(t) >= 80:
        clarity += 15.0
    if not re.search(r"(братан|bro|alpha|sigma|based)", t, re.I):
        clarity += 10.0
    if re.search(r"(что\s+произошло|почему\s+важ|что\s+дальше|why\s+it\s+matters)", t, re.I):
        clarity += 15.0
    clarity = min(100.0, clarity)

    return ReaderSimulationResult(
        reader_relevance_score=relevance,
        reader_unification_score=unification,
        gender_neutral_clarity_score=clarity,
        matched_interests=tuple(sorted(hits.keys())),
        cross_interest_breadth=breadth,
    )
