"""Tier-2 curated SOURCE_CHANNELS — equal credibility and routing."""

from __future__ import annotations

CURATED_SOURCE_CREDIBILITY = 0.75

_CURATED_HANDLES = frozenset(
    {
        "@cb_economics",
        "cb_economics",
        "@tnews365",
        "tnews365",
        "@rbc_news",
        "rbc_news",
        "@vedomosti",
        "vedomosti",
        "@banksta",
        "banksta",
        "@thebell_io",
        "thebell_io",
        "@investingcom",
        "investingcom",
        "@cointelegraph",
        "cointelegraph",
    }
)

_CURATED_BARE = frozenset(h.lstrip("@") for h in _CURATED_HANDLES)


def is_curated_source(channel: str) -> bool:
    key = (channel or "").strip().lower()
    if not key:
        return False
    bare = key.lstrip("@")
    return key in _CURATED_HANDLES or bare in _CURATED_BARE


def curated_source_credibility(channel: str) -> float | None:
    return CURATED_SOURCE_CREDIBILITY if is_curated_source(channel) else None


def curated_handles_for_routing() -> frozenset[str]:
    return _CURATED_HANDLES
