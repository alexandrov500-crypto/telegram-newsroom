"""Source Strategy v2 — T1/T2/T3 signal independence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_T1 = re.compile(r"(reuters|bloomberg|apnews|fed|ecb|цб|sec|oficial|official|regulator|wire)", re.I)
_T2 = re.compile(r"(vedomosti|rbc|kommersant|ft\.com|economist|editorial|analysis)", re.I)
_T3 = re.compile(r"(telegram|t\.me|@|channel|signal|niche|social)", re.I)


@dataclass(frozen=True)
class SourceStrategyResult:
    tier_mix: dict[str, int]
    single_class_only: bool
    allow_flagship: bool
    force_compress: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier_mix": dict(self.tier_mix),
            "single_class_only": self.single_class_only,
            "allow_flagship": self.allow_flagship,
            "force_compress": self.force_compress,
            "reason": self.reason,
        }


def _source_tier(source: str) -> str:
    s = (source or "").lower()
    if _T1.search(s):
        return "T1"
    if _T2.search(s):
        return "T2"
    if _T3.search(s):
        return "T3"
    return "T2"


def evaluate_source_strategy(sources: list[str], *, cluster_size: int = 1) -> SourceStrategyResult:
    tiers: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0}
    for src in sources:
        tiers[_source_tier(src)] += 1

    active = sum(1 for v in tiers.values() if v > 0)
    single = active <= 1 and cluster_size <= 1
    allow_flagship = not single and (tiers["T1"] >= 1 or active >= 2)

    force_compress = single and cluster_size >= 1
    reason = "multi_tier_ok" if not single else "single_class_compress_required"

    return SourceStrategyResult(
        tier_mix=tiers,
        single_class_only=single,
        allow_flagship=allow_flagship,
        force_compress=force_compress,
        reason=reason,
    )
