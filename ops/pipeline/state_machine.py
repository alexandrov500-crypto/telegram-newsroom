"""Strict news item state machine (no ad-hoc boolean gates)."""

from __future__ import annotations

from enum import Enum


class NewsState(str, Enum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    CLUSTERED = "CLUSTERED"
    SCORED = "SCORED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


_ALLOWED: dict[NewsState, frozenset[NewsState]] = {
    NewsState.NEW: frozenset({NewsState.VALIDATED, NewsState.REJECTED}),
    NewsState.VALIDATED: frozenset({NewsState.CLUSTERED, NewsState.REJECTED}),
    NewsState.CLUSTERED: frozenset({NewsState.SCORED, NewsState.REJECTED}),
    NewsState.SCORED: frozenset({NewsState.APPROVED, NewsState.REJECTED}),
    NewsState.APPROVED: frozenset({NewsState.PUBLISHED, NewsState.REJECTED}),
    NewsState.REJECTED: frozenset(),
    NewsState.PUBLISHED: frozenset(),
}


def transition_allowed(current: NewsState | str, target: NewsState | str) -> bool:
    try:
        cur = current if isinstance(current, NewsState) else NewsState(str(current))
        tgt = target if isinstance(target, NewsState) else NewsState(str(target))
    except ValueError:
        return False
    return tgt in _ALLOWED.get(cur, frozenset())


def coerce_state(value: str | NewsState | None, *, default: NewsState = NewsState.NEW) -> NewsState:
    if isinstance(value, NewsState):
        return value
    if not value:
        return default
    try:
        return NewsState(str(value).strip().upper())
    except ValueError:
        return default
