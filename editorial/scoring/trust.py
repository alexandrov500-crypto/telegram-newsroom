"""Source trust from channel reputation store."""

from __future__ import annotations

from editorial.scoring.base import mean_or, normalize_score


def compute_source_trust_score(source_trust_by_channel: dict[str, float]) -> float:
    if not source_trust_by_channel:
        return 0.5
    return mean_or(0.5, list(source_trust_by_channel.values()))
