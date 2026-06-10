"""Universal Value Filter — reject niche-only content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NICHE_TELEGRAM = re.compile(
    r"(наш\s+канал|подписывайтесь|premium|закрытый\s+чат|продолжение\s+в\s+@|"
    r"полный\s+разбор\s+в\s+telegram)",
    re.I,
)
_NO_IMPACT = re.compile(r"(важн|значит|implication|почему|matters|риск|влияет)", re.I)
_LOW_DENSITY = re.compile(r"(.{0,40})$")


@dataclass(frozen=True)
class UniversalValueResult:
    passes: bool
    downgrade_to_digest: bool
    reason: str
    impact_sentence_ok: bool
    cross_domain_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "downgrade_to_digest": self.downgrade_to_digest,
            "reason": self.reason,
            "impact_sentence_ok": self.impact_sentence_ok,
            "cross_domain_ok": self.cross_domain_ok,
        }


def evaluate_universal_value(
    text: str,
    *,
    cross_interest_breadth: int = 0,
    cluster_size: int = 1,
    publishing_mode: str = "core",
) -> UniversalValueResult:
    t = (text or "").strip()
    if not t:
        return UniversalValueResult(False, False, "empty", False, False)

    if _NICHE_TELEGRAM.search(t):
        return UniversalValueResult(False, False, "niche_telegram_only", False, False)

    impact_ok = bool(_NO_IMPACT.search(t))
    cross_ok = cross_interest_breadth >= 2 or cluster_size >= 2

    if not impact_ok and publishing_mode == "core":
        return UniversalValueResult(False, True, "missing_why_it_matters", False, cross_ok)

    if cross_interest_breadth < 1 and cluster_size == 1 and publishing_mode == "core":
        return UniversalValueResult(True, True, "single_domain_downgrade", impact_ok, False)

    if len(t.split()) < 25 and publishing_mode == "core":
        return UniversalValueResult(True, True, "low_density_digest", impact_ok, cross_ok)

    return UniversalValueResult(True, False, "universal_ok", impact_ok, cross_ok)


def impact_in_one_sentence(text: str) -> str:
    t = (text or "").strip()
    for line in t.splitlines():
        line = line.strip()
        if _NO_IMPACT.search(line) and len(line) <= 220:
            return line
    sentences = re.split(r"(?<=[.!?])\s+", t)
    return sentences[0][:200] if sentences else t[:200]
