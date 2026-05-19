from __future__ import annotations

import os
from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class EditorialTemplate:
    key: str
    headline_emoji: str
    insight_label: str
    source_prefix: str


_TEMPLATES: dict[str, EditorialTemplate] = {
    "breaking_news": EditorialTemplate("breaking_news", "🚨", "Latest", "Source"),
    "market_update": EditorialTemplate("market_update", "📈", "Market note", "Source"),
    "geopolitics": EditorialTemplate("geopolitics", "🌍", "Context", "Source"),
    "technology": EditorialTemplate("technology", "💡", "Tech brief", "Source"),
    "economy": EditorialTemplate("economy", "📊", "Context", "Source"),
}


def resolve_editorial_template(
    *,
    source: str | None = None,
    tags: Sequence[str] | None = None,
    override: str | None = None,
) -> EditorialTemplate:
    if override and override in _TEMPLATES:
        return _TEMPLATES[override]
    env = os.getenv("EDITORIAL_TEMPLATE", "").strip().lower()
    if env in _TEMPLATES:
        return _TEMPLATES[env]

    tag_set = {str(t).lower() for t in (tags or [])}
    src = (source or "").lower()

    if "breaking" in tag_set or "urgent" in tag_set:
        return _TEMPLATES["breaking_news"]
    if any(t in tag_set for t in ("geopolitics", "war", "conflict", "ukraine", "gaza")):
        return _TEMPLATES["geopolitics"]
    if any(t in tag_set for t in ("tech", "technology", "ai", "software")):
        return _TEMPLATES["technology"]
    if any(t in tag_set for t in ("markets", "market", "stocks", "finance", "crypto")):
        return _TEMPLATES["market_update"]
    if any(
        t in tag_set
        for t in ("economy", "inflation", "cpi", "fed", "jobs", "gdp", "rates")
    ) or src in ("ap", "reuters", "bloomberg"):
        return _TEMPLATES["economy"]

    return _TEMPLATES["economy"]
