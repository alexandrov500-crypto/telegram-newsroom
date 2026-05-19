from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bot.editorial.flow_health.floor import is_publish_floor_active


class QualityZone(str, Enum):
    HIGH_CONFIDENCE = "high_confidence"
    NORMAL = "normal"
    LOW_CONFIDENCE = "low_confidence"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class ZoneVerdict:
    zone: QualityZone
    quality_floor: float
    trust_floor: float
    allow_with_floor: bool


_SEVERE_BLOCKER_PREFIXES = (
    "hallucination",
    "empty_",
    "broken_",
    "duplicate",
    "title_body",
    "political_misinformation",
    "medical_misinformation",
    "unverified_financial",
    "violent_graphic",
)


def classify_quality_zone(*, quality_score: float, trust_score: float) -> QualityZone:
    if quality_score >= 0.75 and trust_score >= 0.78:
        return QualityZone.HIGH_CONFIDENCE
    if quality_score >= 0.58 and trust_score >= 0.65:
        return QualityZone.NORMAL
    if quality_score >= 0.45 and trust_score >= 0.55:
        return QualityZone.LOW_CONFIDENCE
    return QualityZone.QUARANTINE


def evaluate_zone_gates(
    *,
    quality_score: float,
    trust_score: float,
    blockers: list[str],
) -> ZoneVerdict:
    """Soft zones — borderline content may publish under floor mode."""
    zone = classify_quality_zone(quality_score=quality_score, trust_score=trust_score)
    severe = any(
        any(b.startswith(p) for p in _SEVERE_BLOCKER_PREFIXES) for b in blockers
    )
    if severe:
        return ZoneVerdict(
            zone=QualityZone.QUARANTINE,
            quality_floor=0.75,
            trust_floor=0.75,
            allow_with_floor=False,
        )

    floor = is_publish_floor_active()
    if zone == QualityZone.HIGH_CONFIDENCE:
        return ZoneVerdict(zone=zone, quality_floor=0.65, trust_floor=0.70, allow_with_floor=True)
    if zone == QualityZone.NORMAL:
        return ZoneVerdict(zone=zone, quality_floor=0.58, trust_floor=0.65, allow_with_floor=True)
    if zone == QualityZone.LOW_CONFIDENCE:
        return ZoneVerdict(
            zone=zone,
            quality_floor=0.45,
            trust_floor=0.55,
            allow_with_floor=floor,
        )
    return ZoneVerdict(
        zone=QualityZone.QUARANTINE,
        quality_floor=0.75,
        trust_floor=0.75,
        allow_with_floor=False,
    )


def apply_zone_to_blockers(
    blockers: list[str],
    *,
    quality_score: float,
    trust_score: float,
) -> tuple[list[str], QualityZone]:
    """Remove soft quality_low/trust_low blockers when zone permits."""
    verdict = evaluate_zone_gates(
        quality_score=quality_score,
        trust_score=trust_score,
        blockers=blockers,
    )
    if not verdict.allow_with_floor:
        return blockers, verdict.zone

    out = [b for b in blockers if b not in ("quality_low", "trust_low")]
    if quality_score >= verdict.quality_floor and trust_score >= verdict.trust_floor:
        out = [b for b in out if not b.startswith(("quality_below", "trust_below"))]
    return out, verdict.zone
