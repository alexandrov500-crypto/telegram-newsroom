from __future__ import annotations

import re
from collections.abc import Sequence

MAX_HASHTAGS = 4

_TOPIC_MAP: dict[str, str] = {
    "economy": "Economy",
    "inflation": "Inflation",
    "markets": "Markets",
    "market": "Markets",
    "finance": "Finance",
    "crypto": "Crypto",
    "bitcoin": "Bitcoin",
    "regulation": "Regulation",
    "politics": "Politics",
    "geopolitics": "Geopolitics",
    "war": "Conflict",
    "conflict": "Conflict",
    "technology": "Tech",
    "tech": "Tech",
    "ai": "AI",
    "science": "Science",
    "health": "Health",
    "climate": "Climate",
    "energy": "Energy",
    "breaking": "Breaking",
    "world": "World",
    "us": "USNews",
    "europe": "Europe",
}


def _tokenize_tag(raw: str) -> str:
    t = re.sub(r"[^\w]+", "", raw.strip().lower())
    return t


def normalize_hashtags(
    tags: Sequence[str],
    *,
    source: str | None = None,
    extra_topics: Sequence[str] | None = None,
) -> list[str]:
    """Dedupe and cap hashtags; map raw tags to readable tokens."""
    seen: set[str] = set()
    out: list[str] = []

    def add(label: str) -> None:
        token = _tokenize_tag(label)
        if not token or len(token) < 2:
            return
        mapped = _TOPIC_MAP.get(token, token[:1].upper() + token[1:32])
        key = mapped.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(mapped)

    for t in tags:
        add(str(t))
        if len(out) >= MAX_HASHTAGS:
            return out[:MAX_HASHTAGS]

    if extra_topics:
        for t in extra_topics:
            add(str(t))
            if len(out) >= MAX_HASHTAGS:
                break

    if source and len(out) < MAX_HASHTAGS:
        sk = _tokenize_tag(source)
        if sk and sk not in ("ap", "reuters", "bbc"):
            add(_TOPIC_MAP.get(sk, sk))

    return out[:MAX_HASHTAGS]


def format_hashtag_line(tags: Sequence[str]) -> str:
    labels = normalize_hashtags(tags)
    if not labels:
        return ""
    return " ".join(f"#{label}" for label in labels)
