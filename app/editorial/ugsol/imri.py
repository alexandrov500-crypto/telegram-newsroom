"""Information Market Replacement Index — does the channel replace external info stack?"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ugsol.config import imri_dominance_threshold, imri_recovery_threshold
from app.editorial.ugsol.state import load_state


class IMRIMode(str, Enum):
    DOMINANCE = "dominance"
    STABLE_GROWTH = "stable_growth"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class IMRIState:
    score: float
    trend_7d: float
    segment_breakdown: dict[str, float]
    saturation_risk: float
    mode: IMRIMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "trend_7d": round(self.trend_7d, 2),
            "segment_breakdown": {k: round(v, 2) for k, v in self.segment_breakdown.items()},
            "saturation_risk": round(self.saturation_risk, 2),
            "mode": self.mode.value,
            "formula": {
                "substitution_rate": 0.30,
                "forward_rate": 0.25,
                "save_rate": 0.20,
                "return_frequency": 0.15,
                "cross_domain_coverage": 0.10,
            },
        }


def _trend_7d(runtime_dir: str | None) -> float:
    data = load_state(runtime_dir)
    history = list(data.get("imri_history") or [])
    if len(history) < 2:
        return 0.0
    recent = [float(x.get("score") or 0) for x in history[-7:]]
    older = [float(x.get("score") or 0) for x in history[-14:-7]] if len(history) >= 14 else recent
    r_avg = sum(recent) / len(recent) if recent else 0.0
    o_avg = sum(older) / len(older) if older else r_avg
    return r_avg - o_avg


def compute_imri(
    *,
    runtime_dir: str | None = None,
    substitution_rate: float = 50.0,
    forward_rate: float = 0.0,
    save_rate: float = 0.0,
    return_frequency: float = 0.5,
    cross_domain_coverage: float = 0.4,
    male_resonance: float = 0.5,
    female_resonance: float = 0.5,
) -> IMRIState:
    sub = min(100.0, substitution_rate)
    fwd = min(1.0, forward_rate) * 100.0
    sav = min(1.0, save_rate) * 100.0
    ret = min(1.0, return_frequency) * 100.0
    cross = min(1.0, cross_domain_coverage) * 100.0

    score = (
        0.30 * sub
        + 0.25 * fwd
        + 0.20 * sav
        + 0.15 * ret
        + 0.10 * cross
    )
    score = min(100.0, score)

    trend = _trend_7d(runtime_dir)
    saturation = min(1.0, max(0.0, (score - 85.0) / 15.0)) if score > 85 else 0.0

    dom_thresh = imri_dominance_threshold()
    rec_thresh = imri_recovery_threshold()
    if score >= dom_thresh:
        mode = IMRIMode.DOMINANCE
    elif score >= rec_thresh:
        mode = IMRIMode.STABLE_GROWTH
    else:
        mode = IMRIMode.RECOVERY

    return IMRIState(
        score=score,
        trend_7d=trend,
        segment_breakdown={
            "male_hub": round(male_resonance * 100, 2),
            "female_hub": round(female_resonance * 100, 2),
            "unified": round((male_resonance + female_resonance) * 50, 2),
        },
        saturation_risk=saturation,
        mode=mode,
    )
