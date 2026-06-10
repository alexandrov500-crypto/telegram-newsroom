"""Gender-neutral & universal framing balance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MASCULINE_CODED = re.compile(
    r"(alpha\s+male|sigma|bro\b|bros|based|red\s+pill|hyper\s+masculin)",
    re.I,
)
_LIFESTYLE_SOFT = re.compile(
    r"(beauty\s+tip|relationship\s+advice|horoscope|гороскоп|лайфхак\s+для\s+дев)",
    re.I,
)
_MARKET_JARGON_HEAVY = re.compile(
    r"(gamma\s+squeeze|dark\s+pool|vol\s+surface|skew\s+trade)",
    re.I,
)


@dataclass(frozen=True)
class CommunicationBalance:
    tone_balance_score: float
    clarity_index: float
    universality_index: float
    issues: tuple[str, ...]
    passes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone_balance_score": round(self.tone_balance_score, 2),
            "clarity_index": round(self.clarity_index, 2),
            "universality_index": round(self.universality_index, 2),
            "issues": list(self.issues),
            "passes": self.passes,
        }


def evaluate_communication_balance(text: str) -> CommunicationBalance:
    t = text or ""
    issues: list[str] = []

    tone = 85.0
    if _MASCULINE_CODED.search(t):
        tone -= 25.0
        issues.append("masculine_coded_framing")
    if _LIFESTYLE_SOFT.search(t):
        tone -= 20.0
        issues.append("lifestyle_soft_bias")
    if _MARKET_JARGON_HEAVY.search(t):
        tone -= 15.0
        issues.append("markets_only_jargon")

    clarity = 55.0
    if len(t) >= 100:
        clarity += 15.0
    if re.search(r"(почему|что\s+дальше|важн|значит)", t, re.I):
        clarity += 20.0
    clarity = min(100.0, clarity)

    universality = 60.0
    if not issues:
        universality += 20.0
    if re.search(r"(глобальн|decision|решени|investor|бизнес|полит)", t, re.I):
        universality += 15.0
    universality = min(100.0, universality)

    tone = max(0.0, min(100.0, tone))
    passes = tone >= 55 and clarity >= 50

    return CommunicationBalance(
        tone_balance_score=tone,
        clarity_index=clarity,
        universality_index=universality,
        issues=tuple(issues),
        passes=passes,
    )
