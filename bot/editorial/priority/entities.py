from __future__ import annotations

import re
from collections.abc import Sequence

# Weighted high-signal entity registry (advisory ranking).
ENTITY_WEIGHTS: dict[str, float] = {
    "federal reserve": 0.95,
    "fed": 0.92,
    "sec": 0.9,
    "ecb": 0.88,
    "white house": 0.88,
    "nato": 0.86,
    "china": 0.85,
    "russia": 0.84,
    "ukraine": 0.84,
    "nvidia": 0.9,
    "apple": 0.88,
    "openai": 0.87,
    "microsoft": 0.82,
    "google": 0.82,
    "amazon": 0.8,
    "bitcoin": 0.85,
    "bitcoin etf": 0.9,
    "ethereum": 0.78,
    "treasury": 0.86,
    "opec": 0.82,
    "european union": 0.8,
    "united states": 0.75,
    "boeing": 0.72,
    "tesla": 0.78,
}

_ENTITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(ENTITY_WEIGHTS, key=len, reverse=True)) + r")\b",
    re.I,
)


def score_entity_significance(*texts: str) -> tuple[float, list[str]]:
    blob = " ".join(t for t in texts if t).lower()
    hits: list[str] = []
    best = 0.35
    for match in _ENTITY_RE.finditer(blob):
        key = match.group(1).lower()
        weight = ENTITY_WEIGHTS.get(key, 0.5)
        if weight > best:
            best = weight
        if key not in hits:
            hits.append(key)
    if len(hits) > 1:
        best = min(1.0, best + 0.04 * (len(hits) - 1))
    return round(best, 3), hits[:6]
