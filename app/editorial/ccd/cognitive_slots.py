"""Cognitive slot engine — SIGNAL / CONTEXT / DIGEST / EXPLAINER / REFLECTION."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ccd.weekly_experience_map import DailyMode, TimeBand


class CognitiveSlotType(str, Enum):
    SIGNAL = "signal_slot"
    CONTEXT = "context_slot"
    DIGEST = "digest_slot"
    EXPLAINER = "explainer_slot"
    REFLECTION = "reflection_slot"


@dataclass(frozen=True)
class CognitiveSlot:
    slot_type: CognitiveSlotType
    gravity_min: float
    gravity_max: float
    format_hint: str
    hashtag_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_type": self.slot_type.value,
            "gravity_min": self.gravity_min,
            "gravity_max": self.gravity_max,
            "format_hint": self.format_hint,
            "hashtag_hint": self.hashtag_hint,
        }


def resolve_cognitive_slot(
    *,
    gravity: float,
    daily_mode: DailyMode,
    time_band: TimeBand,
    is_breaking: bool = False,
) -> CognitiveSlot:
    if is_breaking or gravity >= 80:
        return CognitiveSlot(CognitiveSlotType.SIGNAL, 80, 100, "breaking / MarketShock", "#MarketShock")
    if daily_mode == DailyMode.ORIENTATION and time_band == TimeBand.MORNING:
        return CognitiveSlot(CognitiveSlotType.CONTEXT, 60, 79, "explanation + implication", "#GlobalSignal")
    if daily_mode == DailyMode.COMPRESSION or time_band == TimeBand.EVENING:
        if gravity >= 40:
            return CognitiveSlot(CognitiveSlotType.DIGEST, 40, 59, "compression summary", "#MacroFlow")
        return CognitiveSlot(CognitiveSlotType.REFLECTION, 0, 100, "trend framing", "#GlobalSignal")
    if gravity >= 60:
        return CognitiveSlot(CognitiveSlotType.CONTEXT, 60, 79, "explanation + implication", "#GlobalSignal")
    if gravity >= 40:
        return CognitiveSlot(CognitiveSlotType.DIGEST, 40, 59, "compression summary", "#MacroFlow")
    return CognitiveSlot(CognitiveSlotType.EXPLAINER, 0, 100, "deep dive", "#TechSignal")
