"""Habit formation loop — morning brief / evening wrap anchors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ccd.weekly_experience_map import TimeBand


class HabitPhase(str, Enum):
    AWARENESS = "awareness"
    TRUST = "trust"
    RETURN = "return"
    HABIT = "habit"
    DEPENDENCY = "dependency"


class HabitAnchor(str, Enum):
    MORNING_BRIEF = "morning_brief"
    EVENING_WRAP = "evening_wrap"
    BREAKING_INTERRUPT = "breaking_interrupt"
    NONE = "none"


@dataclass(frozen=True)
class HabitLoopState:
    phase: HabitPhase
    anchor: HabitAnchor
    retention_role: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "anchor": self.anchor.value,
            "retention_role": self.retention_role,
        }


def evaluate_habit_loop(
    *,
    time_band: TimeBand,
    is_breaking: bool = False,
    posts_opened_today: int = 0,
    substitution_score: float = 0.0,
) -> HabitLoopState:
    if is_breaking:
        return HabitLoopState(HabitPhase.AWARENESS, HabitAnchor.BREAKING_INTERRUPT, "interrupt_attention")

    if time_band == TimeBand.MORNING:
        phase = HabitPhase.HABIT if posts_opened_today >= 2 else HabitPhase.RETURN
        return HabitLoopState(phase, HabitAnchor.MORNING_BRIEF, "retention_anchor_orientation")

    if time_band == TimeBand.EVENING:
        phase = HabitPhase.DEPENDENCY if substitution_score >= 70 else HabitPhase.HABIT
        return HabitLoopState(phase, HabitAnchor.EVENING_WRAP, "closure_anchor_compression")

    phase = HabitPhase.TRUST if posts_opened_today >= 1 else HabitPhase.RETURN
    return HabitLoopState(phase, HabitAnchor.NONE, "midday_intelligence")
