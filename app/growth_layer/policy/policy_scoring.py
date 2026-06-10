"""Policy scoring and confidence for recommendation types."""

from __future__ import annotations

from enum import Enum
from typing import Any

_ALPHA = 0.05
_HIGH_MIN_SHOWN = 100
_MEDIUM_MIN_SHOWN = 30
_HIGH_MIN_EFFECTIVENESS = 80
_RETIRED_MIN_SHOWN = 30
_RETIRED_MAX_EFFECTIVENESS = 45


class PolicyConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PolicyTier(str, Enum):
    TRUSTED = "TRUSTED"
    EXPERIMENTAL = "EXPERIMENTAL"
    UNVERIFIED = "UNVERIFIED"
    RETIRED = "RETIRED"


_TIER_ORDER = {
    PolicyTier.TRUSTED.value: 0,
    PolicyTier.EXPERIMENTAL.value: 1,
    PolicyTier.UNVERIFIED.value: 2,
    PolicyTier.RETIRED.value: 3,
}


def tier_sort_key(tier: str) -> int:
    return _TIER_ORDER.get(str(tier).upper(), 99)


def calculate_confidence(
    *,
    times_shown: int,
    p_value: float | None,
    effectiveness_score: int,
) -> str:
    if (
        times_shown >= _HIGH_MIN_SHOWN
        and p_value is not None
        and float(p_value) < _ALPHA
        and int(effectiveness_score) >= _HIGH_MIN_EFFECTIVENESS
    ):
        return PolicyConfidence.HIGH.value
    if times_shown >= _MEDIUM_MIN_SHOWN:
        return PolicyConfidence.MEDIUM.value
    return PolicyConfidence.LOW.value


def assign_policy_tier(
    *,
    times_shown: int,
    effectiveness_score: int,
    p_value: float | None,
    err_lift: float | None,
    statistically_significant: bool = False,
) -> str:
    eff = int(effectiveness_score or 0)
    shown = int(times_shown or 0)
    lift = float(err_lift) if err_lift is not None else None

    if shown >= _RETIRED_MIN_SHOWN and eff <= _RETIRED_MAX_EFFECTIVENESS:
        if lift is not None and lift <= 0 and not statistically_significant:
            return PolicyTier.RETIRED.value
        if lift is not None and lift <= -5:
            return PolicyTier.RETIRED.value

    if (
        shown >= _HIGH_MIN_SHOWN
        and p_value is not None
        and float(p_value) < _ALPHA
        and eff >= _HIGH_MIN_EFFECTIVENESS
    ):
        return PolicyTier.TRUSTED.value

    if shown >= _MEDIUM_MIN_SHOWN and (
        (lift is not None and lift > 0)
        or eff >= 60
        or statistically_significant
    ):
        return PolicyTier.EXPERIMENTAL.value

    return PolicyTier.UNVERIFIED.value


def calculate_policy_score(
    *,
    effectiveness_score: int,
    sample_size: int,
    p_value: float | None,
    adoption_rate: float,
) -> int:
    """Composite policy score 0–100 from effectiveness evidence."""
    score = float(effectiveness_score or 0) * 0.55
    sample_component = min(25.0, (int(sample_size or 0) / 100.0) * 25.0)
    score += sample_component
    score += min(10.0, float(adoption_rate or 0) / 10.0)
    if p_value is not None and float(p_value) < _ALPHA:
        score += 10.0
    elif p_value is not None and float(p_value) < 0.1:
        score += 4.0
    return max(0, min(100, int(round(score))))


def build_policy_record(effectiveness_row: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single effectiveness row with confidence, tier, policy_score."""
    times_shown = int(effectiveness_row.get("times_shown") or 0)
    times_adopted = int(effectiveness_row.get("times_adopted") or 0)
    adoption_rate = float(effectiveness_row.get("adoption_rate") or 0)
    eff_score = int(effectiveness_row.get("effectiveness_score") or 0)
    p_value = effectiveness_row.get("p_value")
    err_lift = effectiveness_row.get("err_lift")
    sig = bool(effectiveness_row.get("statistically_significant"))
    rtype = str(effectiveness_row.get("recommendation") or effectiveness_row.get("recommendation_type") or "")

    confidence = calculate_confidence(
        times_shown=times_shown,
        p_value=float(p_value) if p_value is not None else None,
        effectiveness_score=eff_score,
    )
    tier = assign_policy_tier(
        times_shown=times_shown,
        effectiveness_score=eff_score,
        p_value=float(p_value) if p_value is not None else None,
        err_lift=float(err_lift) if err_lift is not None else None,
        statistically_significant=sig,
    )
    policy_score = calculate_policy_score(
        effectiveness_score=eff_score,
        sample_size=times_shown,
        p_value=float(p_value) if p_value is not None else None,
        adoption_rate=adoption_rate,
    )
    return {
        "recommendation_type": rtype,
        "times_shown": times_shown,
        "times_adopted": times_adopted,
        "adoption_rate": adoption_rate,
        "effectiveness_score": eff_score,
        "err_lift": err_lift,
        "forward_lift": effectiveness_row.get("forward_lift"),
        "p_value": p_value,
        "confidence": confidence,
        "tier": tier,
        "policy_score": policy_score,
        "statistically_significant": sig,
    }
