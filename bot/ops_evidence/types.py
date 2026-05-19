from __future__ import annotations

from enum import Enum


class RetirementLabel(str, Enum):
    CANDIDATE_FOR_TUNING = "candidate_for_tuning"
    CANDIDATE_FOR_SUPPRESSION = "candidate_for_suppression"
    CANDIDATE_FOR_REMOVAL = "candidate_for_removal"


class ConfidenceBand(str, Enum):
    FRAGILE = "fragile"
    STABILIZING = "stabilizing"
    STABLE = "stable"
    HIGH_CONFIDENCE = "high_confidence"
