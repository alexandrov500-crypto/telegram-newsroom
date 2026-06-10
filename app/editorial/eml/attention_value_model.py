"""Attention → cognitive value abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AttentionValueState:
    attention_units: float
    substitution_value: float
    trust_accumulation: float
    cognitive_value_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "attention_units": round(self.attention_units, 3),
            "substitution_value": round(self.substitution_value, 3),
            "trust_accumulation": round(self.trust_accumulation, 3),
            "cognitive_value_score": round(self.cognitive_value_score, 3),
        }


def compute_attention_value(
    *,
    substitution_score: float = 50.0,
    imri_score: float = 50.0,
    dual_audience_trust: float = 0.5,
    forward_prediction: float = 0.0,
    experience_fit: float = 0.5,
    is_breaking: bool = False,
) -> AttentionValueState:
    attention = 1.0
    if is_breaking:
        attention = 1.4
    elif experience_fit >= 0.7:
        attention = 1.1

    sub_val = min(1.0, substitution_score / 100.0)
    trust = min(1.0, dual_audience_trust * 0.6 + imri_score / 100.0 * 0.4)
    forward = min(1.0, forward_prediction / 100.0)

    cognitive = (sub_val * 0.40 + trust * 0.35 + forward * 0.15 + experience_fit * 0.10) / attention
    cognitive = min(1.0, cognitive)

    return AttentionValueState(
        attention_units=attention,
        substitution_value=sub_val,
        trust_accumulation=trust,
        cognitive_value_score=cognitive,
    )
