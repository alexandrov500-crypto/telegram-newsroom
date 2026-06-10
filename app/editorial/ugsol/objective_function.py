"""System-wide objective — cognitive replacement, not volume."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SystemObjective:
    """Maximize: substitution × return × resonance × continuity."""

    substitution_per_attention: float
    return_frequency: float
    cross_persona_resonance: float
    temporal_continuity: float
    composite_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "substitution_per_attention": round(self.substitution_per_attention, 3),
            "return_frequency": round(self.return_frequency, 3),
            "cross_persona_resonance": round(self.cross_persona_resonance, 3),
            "temporal_continuity": round(self.temporal_continuity, 3),
            "composite_score": round(self.composite_score, 3),
            "optimizes_for": [
                "habit_formation",
                "channel_substitution_10_20",
                "cognitive_trust",
                "return_behavior",
                "forward_propagation",
            ],
            "not_optimizing_for": [
                "raw_volume",
                "raw_reach",
                "post_count",
                "source_diversity_alone",
            ],
        }


def compute_system_objective(
    *,
    substitution_score: float = 50.0,
    forward_rate: float = 0.0,
    save_rate: float = 0.0,
    return_frequency: float = 0.5,
    dual_audience_trust: float = 0.5,
    continuity_score: float = 0.75,
    attention_units: float = 1.0,
) -> SystemObjective:
    sub_norm = min(1.0, substitution_score / 100.0)
    attention = max(0.1, attention_units)
    sub_per_attn = min(1.0, sub_norm / attention)

    cognitive_signal = min(1.0, (forward_rate * 0.6 + save_rate * 0.4) * 2.0)
    ret = min(1.0, return_frequency)
    resonance = min(1.0, dual_audience_trust)
    continuity = min(1.0, continuity_score)

    composite = sub_per_attn * ret * resonance * continuity
    composite = min(1.0, composite * (0.85 + cognitive_signal * 0.15))

    return SystemObjective(
        substitution_per_attention=sub_per_attn,
        return_frequency=ret,
        cross_persona_resonance=resonance,
        temporal_continuity=continuity,
        composite_score=composite,
    )
