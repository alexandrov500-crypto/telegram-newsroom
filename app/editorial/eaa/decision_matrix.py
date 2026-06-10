"""Autonomy decision matrix — when zero-human publish is allowed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.eaa.config import min_autonomy_confidence, zero_human_mode
from app.editorial.eaa.safety_envelope import SafetyEnvelopeResult


class AutonomyMode(str, Enum):
    HUMAN_REQUIRED = "human_required"
    AI_ASSISTED = "ai_assisted"
    ZERO_HUMAN = "zero_human"


@dataclass(frozen=True)
class AutonomyDecision:
    mode: AutonomyMode
    autonomous_publish: bool
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "autonomous_publish": self.autonomous_publish,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


def resolve_autonomy_decision(
    *,
    control_tower_publish: bool,
    safety: SafetyEnvelopeResult,
    rules_approved: bool,
    ai_confidence: float = 0.0,
    imri_score: float = 50.0,
    cognitive_value: float = 0.5,
    continuity_ok: bool = True,
) -> AutonomyDecision:
    if not control_tower_publish:
        return AutonomyDecision(
            mode=AutonomyMode.HUMAN_REQUIRED,
            autonomous_publish=False,
            confidence=0.0,
            reason="control_tower_reject",
        )

    if not safety.passes:
        return AutonomyDecision(
            mode=AutonomyMode.HUMAN_REQUIRED,
            autonomous_publish=False,
            confidence=0.0,
            reason="safety_envelope_fail",
        )

    conf = max(ai_confidence, cognitive_value * 0.5 + imri_score / 100.0 * 0.3)
    if rules_approved:
        conf = max(conf, 0.72)

    min_conf = min_autonomy_confidence()
    zero_mode = zero_human_mode()

    if zero_mode and rules_approved and safety.passes and continuity_ok and conf >= min_conf:
        return AutonomyDecision(
            mode=AutonomyMode.ZERO_HUMAN,
            autonomous_publish=True,
            confidence=conf,
            reason="zero_human_envelope_pass",
        )

    if rules_approved and conf >= min_conf:
        return AutonomyDecision(
            mode=AutonomyMode.AI_ASSISTED,
            autonomous_publish=True,
            confidence=conf,
            reason="ai_assisted_rules_pass",
        )

    return AutonomyDecision(
        mode=AutonomyMode.HUMAN_REQUIRED,
        autonomous_publish=False,
        confidence=conf,
        reason="confidence_below_threshold",
    )
