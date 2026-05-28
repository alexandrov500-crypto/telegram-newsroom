"""Newsroom editorial identity — niche, tone, publication philosophy (config-driven)."""

from __future__ import annotations

import os
from dataclasses import dataclass


_DEFAULT_NICHES = (
    "macro",
    "business",
    "tech",
    "ai",
    "finance",
    "geopolitics",
)


@dataclass(frozen=True)
class EditorialIdentity:
    """What this channel is — and what it is not."""

    primary_niches: tuple[str, ...]
    tone: str
    philosophy: str
    exclude_general_feed: bool

    def matches_niche(self, category: str) -> bool:
        c = (category or "").strip().lower()
        if not c:
            return False
        return any(n in c or c in n for n in self.primary_niches)

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_niches": list(self.primary_niches),
            "tone": self.tone,
            "philosophy": self.philosophy,
            "exclude_general_feed": self.exclude_general_feed,
        }


def load_editorial_identity() -> EditorialIdentity:
    raw = os.getenv("NEWSROOM_PRIMARY_NICHES", ",".join(_DEFAULT_NICHES))
    niches = tuple(n.strip().lower() for n in raw.replace(";", ",").split(",") if n.strip())
    if not niches:
        niches = _DEFAULT_NICHES
    tone = os.getenv("NEWSROOM_EDITORIAL_TONE", "professional_concise").strip() or "professional_concise"
    philosophy = (
        os.getenv(
            "NEWSROOM_PUBLICATION_PHILOSOPHY",
            "high_signal_curated_newsroom_not_volume_feed",
        ).strip()
        or "high_signal_curated_newsroom_not_volume_feed"
    )
    exclude = os.getenv("NEWSROOM_EXCLUDE_GENERAL_FEED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return EditorialIdentity(
        primary_niches=niches,
        tone=tone,
        philosophy=philosophy,
        exclude_general_feed=exclude,
    )
