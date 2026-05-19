from __future__ import annotations

import re
from collections.abc import Sequence

_TOPIC_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("inflation-fed", ("inflation", "cpi", "ppi", "fed", "federal reserve", "interest rate", "rates")),
    ("ukraine-war", ("ukraine", "russia", "kyiv", "moscow", "nato", "ceasefire", "war")),
    ("ai-regulation", ("ai regulation", "artificial intelligence", "openai", "chatgpt", "eu ai act")),
    ("apple-earnings", ("apple", "aapl", "iphone", "tim cook", "earnings")),
    ("nvidia-chips", ("nvidia", "nvda", "gpu", "chips", "semiconductor", "h100")),
    ("openai-launches", ("openai", "gpt", "model launch", "sam altman")),
    ("markets-risk", ("s&p", "nasdaq", "dow", "stocks", "equities", "selloff", "rally")),
    ("crypto-policy", ("bitcoin", "btc", "ethereum", "crypto", "sec etf")),
    ("energy-oil", ("oil", "crude", "opec", "natural gas", "energy")),
    ("jobs-labor", ("jobs report", "unemployment", "payrolls", "labor market")),
]

_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")


def extract_topic_keys(*texts: str, tags: Sequence[str] | None = None) -> list[str]:
    blob = " ".join(t for t in texts if t).lower()
    if tags:
        blob += " " + " ".join(str(t).lower() for t in tags)
    keys: list[str] = []
    for slug, needles in _TOPIC_PATTERNS:
        if any(n in blob for n in needles):
            keys.append(slug)
    return keys[:4]


def extract_entity_keys(headline: str, summary: str | None = None) -> list[str]:
    blob = f"{headline} {summary or ''}"
    found = {m.group(1).strip() for m in _ENTITY_RE.finditer(blob)}
    return sorted(found)[:8]


def primary_storyline_slug(topic_keys: Sequence[str]) -> str:
    if topic_keys:
        return str(topic_keys[0])
    return "general-news"


def storyline_id_from_slug(slug: str) -> str:
    clean = re.sub(r"[^\w-]+", "-", slug.lower()).strip("-") or "general"
    return f"sl-{clean}"
