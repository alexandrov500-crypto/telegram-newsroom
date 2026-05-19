from __future__ import annotations

import re

from bot.signals.types import CredibilityProfile
from bot.storage.source_repository import SourceProfile
from bot.storage.signal_repository import SignalRepository

_SENSATIONAL = re.compile(
    r"\b(shocking|exclusive|you won't believe|bombshell|insane|unbelievable)\b",
    re.I,
)
_CLICKBAIT = re.compile(r"\b(how to|why you|what happens|secret)\b", re.I)


class CredibilityEngine:
    """Dynamic source credibility from reputation + text patterns."""

    def __init__(self, repository: SignalRepository) -> None:
        self._repo = repository

    def evaluate(
        self,
        *,
        profile: SourceProfile,
        title: str,
        summary: str | None,
    ) -> CredibilityProfile:
        text = f"{title} {summary or ''}"
        sensationalism = 0.0
        if _SENSATIONAL.search(text):
            sensationalism += 0.35
        if _CLICKBAIT.search(text):
            sensationalism += 0.2
        if "!" in title:
            sensationalism += 0.1
        sensationalism = min(1.0, sensationalism)

        trust = profile.trust_score
        approval = profile.approval_ratio
        credibility = max(
            0.0,
            min(1.0, trust * 0.55 + approval * 0.35 - sensationalism * 0.25),
        )
        risk = max(0.0, min(1.0, sensationalism * 0.5 + (1.0 - trust) * 0.4))

        bias_profile = self._bias_profile(profile.source_type, text)

        snap = CredibilityProfile(
            credibility_score=credibility,
            risk_score=risk,
            bias_profile=bias_profile,
            sensationalism=sensationalism,
        )
        self._repo.upsert_credibility(
            source_name=profile.source_name,
            credibility_score=credibility,
            risk_score=risk,
            bias_profile=bias_profile,
            sensationalism=sensationalism,
        )
        return snap

    @staticmethod
    def _bias_profile(source_type: str, text: str) -> dict[str, float]:
        lower = text.lower()
        geo = 0.3 if any(
            w in lower for w in ("russia", "china", "nato", "ukraine", "israel")
        ) else 0.05
        market = 0.3 if any(
            w in lower for w in ("stock", "bitcoin", "fed", "etf", "market")
        ) else 0.05
        tech = 0.25 if any(w in lower for w in ("ai", "openai", "nvidia", "chip")) else 0.05
        if source_type == "telegram":
            geo *= 1.1
        return {
            "geopolitical": min(1.0, geo),
            "market": min(1.0, market),
            "technology": min(1.0, tech),
        }
