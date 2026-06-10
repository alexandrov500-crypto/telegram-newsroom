"""UEOS Score — final editorial decision metric."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.unified_operating_system.config import (
    ueos_digest_threshold,
    ueos_flagship_threshold,
    ueos_publish_threshold,
    ueos_stability_fallback_threshold,
)


class UEOSAction(str, Enum):
    PUBLISH_FLAGSHIP = "publish_flagship"
    PUBLISH = "publish"
    PUBLISH_DIGEST = "publish_digest"
    COMPRESS_AND_PUBLISH = "compress_and_publish"
    DELAY = "delay"
    REJECT = "reject"
    STABILITY_FALLBACK = "stability_fallback"


@dataclass(frozen=True)
class UEOSScoreBreakdown:
    ues: float
    crs: float
    gravity: float
    reader_unification: float
    cross_source_intelligence: float
    attention_design: float
    total: float
    action: UEOSAction
    skip_cadence_cap: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ues": round(self.ues, 2),
            "crs": round(self.crs, 2),
            "gravity": round(self.gravity, 2),
            "reader_unification": round(self.reader_unification, 2),
            "cross_source_intelligence": round(self.cross_source_intelligence, 2),
            "attention_design": round(self.attention_design, 2),
            "total": round(self.total, 2),
            "action": self.action.value,
            "skip_cadence_cap": self.skip_cadence_cap,
            "objective": "maximize_cognitive_replacement_of_external_information_ecosystem",
        }


def _attention_design_score(attention: dict[str, Any]) -> float:
    score = 35.0
    if attention.get("has_hook"):
        score += 22.0
    if attention.get("has_meaning"):
        score += 22.0
    if attention.get("has_implication"):
        score += 21.0
    if attention.get("passes"):
        score += 10.0
    return min(100.0, score)


def compute_ueos_score(
    *,
    ues_total: float,
    crs_total: float,
    gravity_total: float,
    reader_unification: float,
    cross_source_intelligence: float,
    attention_design: dict[str, Any] | None = None,
    compress_mode: bool = False,
    publishing_mode: str = "core",
) -> UEOSScoreBreakdown:
    att_score = _attention_design_score(attention_design or {})

    total = (
        0.25 * ues_total
        + 0.20 * crs_total
        + 0.20 * gravity_total
        + 0.15 * reader_unification
        + 0.10 * cross_source_intelligence
        + 0.10 * att_score
    )
    total = max(0.0, min(100.0, total))

    flagship_thr = float(ueos_flagship_threshold())
    publish_thr = float(ueos_publish_threshold())
    digest_thr = float(ueos_digest_threshold())
    fallback_thr = float(ueos_stability_fallback_threshold())

    skip_cap = False
    if compress_mode and total >= digest_thr:
        action = UEOSAction.COMPRESS_AND_PUBLISH
    elif total >= flagship_thr:
        action = UEOSAction.PUBLISH_FLAGSHIP
        skip_cap = True
    elif total >= publish_thr:
        action = UEOSAction.PUBLISH
    elif total >= digest_thr:
        action = UEOSAction.PUBLISH_DIGEST
    elif total >= fallback_thr:
        action = UEOSAction.STABILITY_FALLBACK
    elif publishing_mode in {"elastic_fill", "editorial_synthesis"}:
        action = UEOSAction.STABILITY_FALLBACK
    else:
        action = UEOSAction.REJECT

    return UEOSScoreBreakdown(
        ues=ues_total,
        crs=crs_total,
        gravity=gravity_total,
        reader_unification=reader_unification,
        cross_source_intelligence=cross_source_intelligence,
        attention_design=att_score,
        total=total,
        action=action,
        skip_cadence_cap=skip_cap,
    )
