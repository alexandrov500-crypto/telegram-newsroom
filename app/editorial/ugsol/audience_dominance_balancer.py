"""Audience dominance balancer — male/female hub weight equilibrium."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ugsol.config import female_hub_base_weight, male_hub_base_weight


class CorrectionAction(str, Enum):
    NONE = "none"
    BOOST_FEMALE_FRAMING = "boost_female_framing"
    BOOST_MALE_FRAMING = "boost_male_framing"
    UNIFIED_CORE = "unified_core"


@dataclass(frozen=True)
class AudienceBalanceState:
    male_weight: float
    female_weight: float
    drift: float
    correction_action: CorrectionAction
    segment_forward_male: float
    segment_forward_female: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "male_weight": round(self.male_weight, 3),
            "female_weight": round(self.female_weight, 3),
            "drift": round(self.drift, 3),
            "correction_action": self.correction_action.value,
            "segment_forward_male": round(self.segment_forward_male, 3),
            "segment_forward_female": round(self.segment_forward_female, 3),
            "principle": "universal_core_adaptive_framing_not_split_content",
        }


def evaluate_audience_balance(
    *,
    mpaes_segments: dict[str, Any] | None = None,
    forward_rate_male: float = 0.0,
    forward_rate_female: float = 0.0,
    save_rate_male: float = 0.0,
    save_rate_female: float = 0.0,
    engagement_depth: float = 0.5,
) -> AudienceBalanceState:
    male_w = male_hub_base_weight()
    female_w = female_hub_base_weight()
    total = male_w + female_w
    male_w /= total
    female_w /= total

    male_signal = forward_rate_male * 0.6 + save_rate_male * 0.3 + engagement_depth * 0.1
    female_signal = forward_rate_female * 0.6 + save_rate_female * 0.3 + engagement_depth * 0.1

    if mpaes_segments and isinstance(mpaes_segments.get("segments"), list):
        for seg in mpaes_segments["segments"]:
            if not isinstance(seg, dict):
                continue
            name = str(seg.get("segment") or "")
            rel = float(seg.get("relevance_score") or 50) / 100.0
            if name == "hub_male":
                male_signal = max(male_signal, rel * 0.5)
            elif name == "hub_female":
                female_signal = max(female_signal, rel * 0.5)

    signal_sum = male_signal + female_signal + 0.01
    male_perf = male_signal / signal_sum
    female_perf = female_signal / signal_sum

    drift = male_perf - female_perf
    correction = CorrectionAction.NONE

    if drift > 0.12:
        female_w = min(0.58, female_w + 0.03)
        male_w = 1.0 - female_w
        correction = CorrectionAction.BOOST_FEMALE_FRAMING
    elif drift < -0.12:
        male_w = min(0.62, male_w + 0.03)
        female_w = 1.0 - male_w
        correction = CorrectionAction.BOOST_MALE_FRAMING
    else:
        correction = CorrectionAction.UNIFIED_CORE

    return AudienceBalanceState(
        male_weight=male_w,
        female_weight=female_w,
        drift=drift,
        correction_action=correction,
        segment_forward_male=forward_rate_male,
        segment_forward_female=forward_rate_female,
    )
