"""Hard safety bounds for zero-human editorial autonomy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.eaa.config import safety_envelope_strict


@dataclass(frozen=True)
class SafetyEnvelopeResult:
    passes: bool
    violations: tuple[str, ...]
    risk_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "violations": list(self.violations),
            "risk_score": round(self.risk_score, 3),
        }


_UNVERIFIED = re.compile(r"(unconfirmed|слух|rumou?r|не\s+подтвержд)", re.I)
_SPAM = re.compile(r"(подписывайтесь|subscribe\s+now|реклама|promo\s+code)", re.I)
_HARM = re.compile(r"(kill\s+all|genocide\s+is\s+good|buy\s+now\s+100x)", re.I)


def evaluate_safety_envelope(body: str, *, is_breaking: bool = False) -> SafetyEnvelopeResult:
    text = body or ""
    violations: list[str] = []
    risk = 0.0

    if len(text.strip()) < 60:
        violations.append("content_too_short")
        risk += 0.35
    if _UNVERIFIED.search(text) and is_breaking:
        violations.append("unverified_breaking")
        risk += 0.40
    if _SPAM.search(text):
        violations.append("spam_pattern")
        risk += 0.30
    if _HARM.search(text):
        violations.append("harm_pattern")
        risk += 0.90

    if safety_envelope_strict() and "unverified_breaking" in violations:
        risk += 0.15

    risk = min(1.0, risk)
    passes = risk < 0.45 and "harm_pattern" not in violations

    return SafetyEnvelopeResult(passes=passes, violations=tuple(violations), risk_score=risk)
