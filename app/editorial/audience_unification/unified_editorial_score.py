"""Unified Editorial Score (UES) — composite publish decision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.audience_unification.config import (
    ues_digest_threshold,
    ues_normal_publish_threshold,
    ues_publish_immediate_threshold,
)


@dataclass(frozen=True)
class UESBreakdown:
    gravity: float
    crs: float
    reader_relevance: float
    clarity: float
    source_independence: float
    total: float
    action: str
    publish_immediately: bool
    force_digest: bool
    reject: bool
    flagship: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "gravity": round(self.gravity, 2),
            "crs": round(self.crs, 2),
            "reader_relevance": round(self.reader_relevance, 2),
            "clarity": round(self.clarity, 2),
            "source_independence": round(self.source_independence, 2),
            "total": round(self.total, 2),
            "action": self.action,
            "publish_immediately": self.publish_immediately,
            "force_digest": self.force_digest,
            "reject": self.reject,
            "flagship": self.flagship,
            "objective": "maximize_cross_source_cognitive_replacement",
        }


def compute_ues(
    *,
    gravity_total: float,
    crs_total: float,
    reader_relevance: float,
    clarity: float,
    source_independence: float = 1.0,
    crs_flagship: bool = False,
    publishing_mode: str = "core",
) -> UESBreakdown:
    independence_pct = max(0.0, min(100.0, source_independence * 100.0))
    total = (
        0.30 * gravity_total
        + 0.25 * crs_total
        + 0.20 * reader_relevance
        + 0.15 * clarity
        + 0.10 * independence_pct
    )
    total = max(0.0, min(100.0, total))

    immediate_thr = float(ues_publish_immediate_threshold())
    normal_thr = float(ues_normal_publish_threshold())
    digest_thr = float(ues_digest_threshold())

    reject = False
    force_digest = False
    immediate = False
    flagship = crs_flagship or total >= immediate_thr + 3

    if total >= immediate_thr:
        action = "publish_immediately"
        immediate = True
    elif total >= normal_thr:
        action = "normal_publish"
    elif total >= digest_thr:
        action = "digest_slot"
        force_digest = True
    else:
        action = "reject"
        reject = publishing_mode == "core"

    if publishing_mode in {"elastic_fill", "editorial_synthesis"} and action == "reject":
        reject = False
        force_digest = True
        action = "digest_slot_stability_override"

    return UESBreakdown(
        gravity=gravity_total,
        crs=crs_total,
        reader_relevance=reader_relevance,
        clarity=clarity,
        source_independence=independence_pct,
        total=total,
        action=action,
        publish_immediately=immediate,
        force_digest=force_digest,
        reject=reject,
        flagship=flagship,
    )
