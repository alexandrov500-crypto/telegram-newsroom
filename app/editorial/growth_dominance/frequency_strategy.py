"""Demand-driven editorial frequency strategy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.growth_dominance.config import (
    high_signal_posts_max,
    low_signal_posts_min,
    normal_flow_posts_max,
)


class FrequencyMode(str, Enum):
    NORMAL = "normal_flow"
    HIGH_SIGNAL = "high_signal_day"
    LOW_SIGNAL = "low_signal_day"


@dataclass(frozen=True)
class FrequencyPlan:
    mode: FrequencyMode
    daily_cap: int
    min_posts: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "daily_cap": self.daily_cap,
            "min_posts": self.min_posts,
            "reason": self.reason,
        }


def resolve_frequency_plan(
    *,
    high_gravity_events_today: int = 0,
    avg_gravity_today: float = 0.0,
    posts_today: int = 0,
) -> FrequencyPlan:
    if high_gravity_events_today >= 2 or avg_gravity_today >= 72:
        return FrequencyPlan(
            mode=FrequencyMode.HIGH_SIGNAL,
            daily_cap=high_signal_posts_max(),
            min_posts=normal_flow_posts_max(),
            reason="high_gravity_day",
        )
    if avg_gravity_today < 48 and posts_today >= low_signal_posts_min():
        return FrequencyPlan(
            mode=FrequencyMode.LOW_SIGNAL,
            daily_cap=low_signal_posts_min() + 2,
            min_posts=low_signal_posts_min(),
            reason="low_signal_synthesis_focus",
        )
    return FrequencyPlan(
        mode=FrequencyMode.NORMAL,
        daily_cap=normal_flow_posts_max(),
        min_posts=low_signal_posts_min(),
        reason="normal_flow",
    )
