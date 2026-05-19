from __future__ import annotations

from enum import Enum

SUBSYSTEMS = (
    "editorial_quality",
    "memory_matching",
    "contradiction_detection",
    "prioritization",
    "fatigue_detection",
    "source_trust",
    "runtime_watchdog",
)


class TrustBand(str, Enum):
    HIGHLY_RELIABLE = "highly_reliable"
    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    LOW_CONFIDENCE = "low_confidence"


def band_for_scores(*, reliability: float, precision: float, stability: float) -> TrustBand:
    if reliability >= 0.75 and precision >= 0.55 and stability >= 0.6:
        return TrustBand.HIGHLY_RELIABLE
    if reliability >= 0.55 and precision >= 0.4:
        return TrustBand.STABLE
    if reliability >= 0.35:
        return TrustBand.EXPERIMENTAL
    return TrustBand.LOW_CONFIDENCE
