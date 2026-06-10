"""Virality tier bands (0–100)."""

from __future__ import annotations

import os
from enum import Enum


class ViralityTier(str, Enum):
    STANDARD = "standard"
    ENHANCED = "enhanced"
    VIRAL_CANDIDATE = "viral_candidate"


def _enhanced_min() -> int:
    try:
        return max(1, min(99, int(os.getenv("VIRALITY_ENHANCED_MIN", "41"))))
    except ValueError:
        return 41


def _viral_min() -> int:
    try:
        return max(2, min(100, int(os.getenv("VIRALITY_VIRAL_MIN", "71"))))
    except ValueError:
        return 71


def classify_virality_tier(score: int) -> ViralityTier:
    s = max(0, min(100, int(score)))
    viral_min = _viral_min()
    enhanced_min = _enhanced_min()
    if s >= viral_min:
        return ViralityTier.VIRAL_CANDIDATE
    if s >= enhanced_min:
        return ViralityTier.ENHANCED
    return ViralityTier.STANDARD
