"""Source authority tiers for signal-first ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.curated_sources import curated_handles_for_routing

# Tier 1 — wire services, major financial press, official agencies
_TIER1_PATTERNS = re.compile(
    r"(reuters|bloomberg|wsj|wall\s*street|financialtimes|\bft\b|apnews|associated\s+press|"
    r"afp\b|tass\b|interfax|росстат|цб\s*рф|cbr\.ru|minfin|sec\.gov|ecb\.europa)",
    re.I,
)

# Tier 2 — curated Telegram / analyst handles (extend via env)
_DEFAULT_TIER2 = curated_handles_for_routing()


@dataclass(frozen=True)
class SourceTierInfo:
    tier: int  # 1 | 2 | 3
    authority: float  # 0..1
    primary_handle: str | None
    channel_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "authority": round(self.authority, 4),
            "primary_handle": self.primary_handle,
            "channel_count": self.channel_count,
        }


def _normalize_handle(channel: str) -> str:
    ch = (channel or "").strip()
    if not ch:
        return ""
    return ch if ch.startswith("@") else f"@{ch.lstrip('@')}"


def _tier2_handles() -> frozenset[str]:
    import os

    extra = os.getenv("NEWSROOM_TIER2_CHANNELS", "").strip()
    if not extra:
        return _DEFAULT_TIER2
    out = set(_DEFAULT_TIER2)
    for part in extra.replace(";", ",").split(","):
        p = part.strip().lower()
        if p:
            out.add(p if p.startswith("@") else f"@{p}")
            out.add(p.lstrip("@"))
    return frozenset(out)


def classify_source(channel: str, *, runtime_dir: str | None = None) -> tuple[int, float]:
    """Return (tier, authority_score) for a single channel handle."""
    handle = _normalize_handle(channel)
    key = handle.lower()
    bare = key.lstrip("@")

    if _TIER1_PATTERNS.search(bare) or _TIER1_PATTERNS.search(key):
        return 1, 0.92

    tier2 = _tier2_handles()
    if key in tier2 or bare in tier2:
        return 2, 0.72

    try:
        from utils.source_reputation import export_channel_scores_for_priority

        rep = export_channel_scores_for_priority(runtime_dir)
        row = rep.get(handle) or rep.get(bare) or {}
        if isinstance(row, dict) and row.get("score") is not None:
            score = float(row["score"])
            if score >= 0.75:
                return 2, round(min(0.88, score), 4)
            if score >= 0.55:
                return 3, round(max(0.35, score), 4)
            return 3, round(max(0.2, score * 0.85), 4)
    except Exception:
        pass

    return 3, 0.28


def aggregate_source_tier(
    sources: list[str] | None,
    *,
    runtime_dir: str | None = None,
) -> SourceTierInfo:
    """Best tier among sources (lowest number = highest authority)."""
    srcs = list(sources or [])
    if not srcs:
        return SourceTierInfo(tier=3, authority=0.35, primary_handle=None, channel_count=0)

    tiers: list[tuple[int, float, str]] = []
    for s in srcs:
        h = _normalize_handle(s)
        if not h:
            continue
        t, a = classify_source(h, runtime_dir=runtime_dir)
        tiers.append((t, a, h))

    if not tiers:
        return SourceTierInfo(tier=3, authority=0.35, primary_handle=None, channel_count=0)

    best = min(tiers, key=lambda x: (x[0], -x[1]))
    primary = best[2]
    avg_auth = sum(x[1] for x in tiers) / len(tiers)
    return SourceTierInfo(
        tier=best[0],
        authority=round(max(best[1], avg_auth * 0.9), 4),
        primary_handle=primary,
        channel_count=len(set(t[2] for t in tiers)),
    )
