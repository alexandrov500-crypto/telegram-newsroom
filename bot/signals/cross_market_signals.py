from __future__ import annotations

import re
from dataclasses import dataclass

_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "ai": re.compile(r"\b(ai|openai|nvidia|llm|chip|semiconductor)\b", re.I),
    "crypto": re.compile(r"\b(bitcoin|ethereum|crypto|sec|etf)\b", re.I),
    "macro": re.compile(r"\b(fed|inflation|gdp|treasury|rate hike)\b", re.I),
    "cyber": re.compile(r"\b(hack|breach|ransomware|cyber)\b", re.I),
    "geopolitics": re.compile(
        r"\b(war|sanction|nato|ukraine|russia|middle east|oil)\b",
        re.I,
    ),
}

_CROSS_LINKS: tuple[tuple[str, str, str], ...] = (
    ("ai", "crypto", "AI narrative may move crypto risk assets"),
    ("geopolitics", "macro", "Geopolitical escalation may affect macro/oil"),
    ("geopolitics", "crypto", "Geopolitical shock may drive crypto volatility"),
    ("ai", "macro", "Semiconductor/AI earnings may affect macro sentiment"),
)


@dataclass(frozen=True)
class CrossMarketSignal:
    left_domain: str
    right_domain: str
    description: str
    strength: float


def classify_domains(text: str) -> set[str]:
    domains: set[str] = set()
    for name, pattern in _DOMAIN_PATTERNS.items():
        if pattern.search(text):
            domains.add(name)
    return domains


def detect_cross_market_signals(text: str, *, velocity: float = 0.0) -> list[CrossMarketSignal]:
    domains = classify_domains(text)
    signals: list[CrossMarketSignal] = []
    for left, right, desc in _CROSS_LINKS:
        if left in domains and right in domains:
            strength = min(1.0, 0.55 + velocity * 0.3)
            signals.append(
                CrossMarketSignal(
                    left_domain=left,
                    right_domain=right,
                    description=desc,
                    strength=strength,
                ),
            )
    return signals
