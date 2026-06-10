"""Growth feedback reinjection — learn from replacement signals, not raw views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.ugsol.state import load_state, save_state


@dataclass(frozen=True)
class FeedbackAdjustments:
    egdl_gravity_bias: float
    auh_compression_strength: float
    mpaes_framing_bias: str
    peos_substitution_threshold_delta: float
    reasoning: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "egdl_gravity_bias": round(self.egdl_gravity_bias, 3),
            "auh_compression_strength": round(self.auh_compression_strength, 3),
            "mpaes_framing_bias": self.mpaes_framing_bias,
            "peos_substitution_threshold_delta": round(self.peos_substitution_threshold_delta, 2),
            "reasoning": list(self.reasoning),
            "signal_source": "cognitive_replacement_not_raw_views",
        }


def compute_feedback_adjustments(
    *,
    runtime_dir: str | None = None,
    forward_rate: float = 0.0,
    save_rate: float = 0.0,
    return_rate: float = 0.0,
    ctr_proxy: float = 0.0,
    male_resonance: float = 0.5,
    female_resonance: float = 0.5,
    imri_score: float = 50.0,
) -> FeedbackAdjustments:
    data = load_state(runtime_dir)
    feedback = dict(data.get("feedback_ema") or {})

    cognitive = forward_rate * 0.45 + save_rate * 0.35 + return_rate * 0.20
    prev_cognitive = float(feedback.get("cognitive_signal") or cognitive)
    ema = prev_cognitive * 0.7 + cognitive * 0.3

    reasoning: list[str] = []
    egdl_bias = 0.0
    auh_strength = 0.5
    mpaes_bias = "unified"
    peos_delta = 0.0

    if ema >= 0.6:
        egdl_bias = 0.05
        peos_delta = -3.0
        reasoning.append("high_replacement_signal:lower_peos_threshold")
    elif ema < 0.3:
        egdl_bias = -0.03
        auh_strength = 0.65
        peos_delta = 5.0
        reasoning.append("low_replacement_signal:compress_and_raise_bar")

    if male_resonance > female_resonance + 0.1:
        mpaes_bias = "boost_female_framing"
        reasoning.append("segment_drift:female_framing_correction")
    elif female_resonance > male_resonance + 0.1:
        mpaes_bias = "boost_male_framing"
        reasoning.append("segment_drift:male_framing_correction")

    if imri_score < 60:
        auh_strength = min(0.8, auh_strength + 0.1)
        reasoning.append("imri_recovery:stronger_compression")

    if ctr_proxy > 0.7 and cognitive < 0.3:
        reasoning.append("ctr_without_replacement:ignored_ctr")

    feedback["cognitive_signal"] = ema
    data["feedback_ema"] = feedback
    save_state(runtime_dir, data)

    return FeedbackAdjustments(
        egdl_gravity_bias=egdl_bias,
        auh_compression_strength=auh_strength,
        mpaes_framing_bias=mpaes_bias,
        peos_substitution_threshold_delta=peos_delta,
        reasoning=tuple(reasoning or ["baseline_no_adjustment"]),
    )
