from __future__ import annotations

import re

from bot.signals.types import ImpactProfile

_GEO = re.compile(
    r"\b(war|sanction|nato|invasion|missile|ceasefire|embargo|election|nuclear)\b",
    re.I,
)
_MARKET = re.compile(
    r"\b(etf|fed|bitcoin|ethereum|nasdaq|crash|rally|ipo|sec|treasury|inflation)\b",
    re.I,
)
_TECH = re.compile(r"\b(ai|openai|nvidia|chip|llm|semiconductor|cyber)\b", re.I)
_CYBER = re.compile(r"\b(hack|breach|ransomware|malware|zero-day|outage)\b", re.I)
_SOCIAL = re.compile(r"\b(protest|election|referendum|strike|ban)\b", re.I)


def analyze_impact(
    *,
    title: str,
    summary: str | None,
    tags: list[str],
    trend_velocity: float = 0.0,
) -> ImpactProfile:
    text = f"{title} {summary or ''} {' '.join(tags)}"
    geo = 0.85 if _GEO.search(text) else 0.2
    market = 0.82 if _MARKET.search(text) else 0.25
    tech = 0.75 if _TECH.search(text) else 0.2
    cyber = 0.8 if _CYBER.search(text) else 0.15
    social = 0.65 if _SOCIAL.search(text) else 0.2
    ai_impact = min(1.0, tech * 0.9 + (0.15 if "ai" in text.lower() else 0))

    boost = min(0.15, trend_velocity * 0.15)
    return ImpactProfile(
        market_impact=min(1.0, market + boost),
        geopolitical_impact=min(1.0, geo + boost),
        technological_impact=min(1.0, tech + boost),
        social_impact=min(1.0, social + boost),
        cyber_risk=min(1.0, cyber + boost),
        ai_ecosystem_impact=min(1.0, ai_impact + boost),
    )
