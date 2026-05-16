"""Lightweight diversity signals for policy / pipeline (no ML)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from db.models import RawPost


@dataclass(slots=True)
class DiversitySignals:
    unique_channels: int
    unique_channel_ratio: float
    channel_concentration: float  # max share of posts from one channel (0–1)
    entity_token_repetition: float  # 0–1 from normalized entity list
    geographic_markers: tuple[str, ...]


def compute_diversity_signals(
    posts: list[RawPost],
    topic_hint: str,
    entity_norms: list[str] | tuple[str, ...],
) -> DiversitySignals:
    n_posts = max(1, len(posts))
    chans = [str(p.channel_name or "").strip().lower() for p in posts if str(p.channel_name or "").strip()]
    uniq = len(set(chans))
    freq = Counter(chans)
    top_share = max(freq.values()) / n_posts if freq else 1.0
    c = Counter(str(x).lower() for x in entity_norms if str(x).strip())
    rep = max(c.values()) if c else 1
    ent_rep = min(1.0, max(0.0, (rep - 1) / 5.0))
    hay = f"{topic_hint} {' '.join(entity_norms)}".lower()
    markers = ("usa", "uk", "eu", "china", "russia", "india", "germany", "france", "japan")
    geo = tuple(m for m in markers if m in hay)
    return DiversitySignals(
        unique_channels=uniq,
        unique_channel_ratio=round(uniq / n_posts, 4),
        channel_concentration=round(top_share, 4),
        entity_token_repetition=round(ent_rep, 4),
        geographic_markers=geo,
    )
