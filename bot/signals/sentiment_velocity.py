from __future__ import annotations

import re

_POSITIVE = re.compile(
    r"\b(rally|surge|optimism|recovery|breakthrough|approved|peace|ceasefire|gain)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(crash|panic|fear|war|invasion|sanction|collapse|crisis|hack|outage|plunge)\b",
    re.I,
)
_FEAR = re.compile(r"\b(panic|fear|crisis|emergency|collapse|war)\b", re.I)
_EUPHORIA = re.compile(r"\b(surge|rally|record high|boom|euphoria|all-time)\b", re.I)


def sentiment_score(text: str) -> float:
    """Lexical sentiment in [-1, 1]."""
    if not text.strip():
        return 0.0
    pos = len(_POSITIVE.findall(text))
    neg = len(_NEGATIVE.findall(text))
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


def sentiment_velocity(previous: float, current: float) -> float:
    """Rate of sentiment change."""
    return max(-1.0, min(1.0, current - previous))


def detect_sentiment_regime(text: str, *, velocity: float) -> str | None:
    if _FEAR.search(text) and velocity < -0.25:
        return "panic"
    if _EUPHORIA.search(text) and velocity > 0.25:
        return "market_euphoria"
    if velocity < -0.4:
        return "narrative_collapse"
    if velocity > 0.4:
        return "optimism_spike"
    return None
