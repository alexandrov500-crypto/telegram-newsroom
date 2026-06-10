"""Editorial state machine — signal / normal / low / anti-pause / synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.osgcp.config import (
    anti_pause_gap_trigger,
    gravity_low_threshold,
    gravity_signal_threshold,
)


class EditorialStateKind(str, Enum):
    SIGNAL = "signal_state"
    NORMAL = "normal_state"
    LOW_SIGNAL = "low_signal_state"
    ANTI_PAUSE = "anti_pause_state"
    SYNTHESIS = "synthesis_state"


@dataclass(frozen=True)
class EditorialState:
    current_state: EditorialStateKind
    reason: str
    confidence: float
    fallback_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "fallback_mode": self.fallback_mode,
        }


def resolve_editorial_state(
    *,
    gravity_avg: float,
    gap_minutes: float | None,
    desk_rejects_consecutive: int = 0,
    publishing_mode: str = "core",
    anti_pause_active: bool = False,
) -> EditorialState:
    gap = gap_minutes if gap_minutes is not None else 0.0
    trigger = anti_pause_gap_trigger()

    if publishing_mode == "editorial_synthesis" or desk_rejects_consecutive >= 3:
        return EditorialState(
            EditorialStateKind.SYNTHESIS,
            "desk_rejects_or_synthesis_mode",
            0.9,
            "synthesis",
        )
    if anti_pause_active or gap >= trigger:
        return EditorialState(
            EditorialStateKind.ANTI_PAUSE,
            "gap_exceeds_anti_pause_threshold",
            0.95,
            "elastic_fill",
        )
    if gravity_avg >= gravity_signal_threshold():
        return EditorialState(
            EditorialStateKind.SIGNAL,
            "high_gravity_avg",
            0.85,
            "signal",
        )
    if gravity_avg < gravity_low_threshold():
        return EditorialState(
            EditorialStateKind.LOW_SIGNAL,
            "low_gravity_avg",
            0.8,
            "digest",
        )
    return EditorialState(
        EditorialStateKind.NORMAL,
        "normal_flow",
        0.75,
        "context",
    )
