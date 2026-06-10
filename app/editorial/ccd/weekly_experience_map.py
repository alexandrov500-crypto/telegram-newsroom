"""7-day editorial experience map — predictable cognitive rhythm."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class TimeBand(str, Enum):
    MORNING = "morning"
    MIDDAY = "midday"
    EVENING = "evening"


class DailyMode(str, Enum):
    ORIENTATION = "orientation"
    INTELLIGENCE = "intelligence"
    COMPRESSION = "compression"


_WEEKLY_FOCUS: dict[DayOfWeek, str] = {
    DayOfWeek.MONDAY: "macro_reset",
    DayOfWeek.TUESDAY: "tech_ai_acceleration",
    DayOfWeek.WEDNESDAY: "market_policy_interaction",
    DayOfWeek.THURSDAY: "geopolitical_structural_shifts",
    DayOfWeek.FRIDAY: "business_earnings_review",
    DayOfWeek.SATURDAY: "deep_explainers_synthesis",
    DayOfWeek.SUNDAY: "future_trends_reflection",
}

_TIME_MODE: dict[TimeBand, DailyMode] = {
    TimeBand.MORNING: DailyMode.ORIENTATION,
    TimeBand.MIDDAY: DailyMode.INTELLIGENCE,
    TimeBand.EVENING: DailyMode.COMPRESSION,
}

_TIME_PURPOSE: dict[TimeBand, str] = {
    TimeBand.MORNING: "что происходит в мире сейчас",
    TimeBand.MIDDAY: "что меняется прямо сейчас",
    TimeBand.EVENING: "что это значит",
}


@dataclass(frozen=True)
class WeeklyExperienceSlot:
    day: DayOfWeek
    time_band: TimeBand
    daily_mode: DailyMode
    cognitive_focus: str
    purpose: str
    preferred_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.value,
            "time_band": self.time_band.value,
            "daily_mode": self.daily_mode.value,
            "cognitive_focus": self.cognitive_focus,
            "purpose": self.purpose,
            "preferred_categories": list(self.preferred_categories),
        }


_FOCUS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "macro_reset": ("macro", "markets", "geopolitics"),
    "tech_ai_acceleration": ("ai", "tech", "markets"),
    "market_policy_interaction": ("markets", "macro", "business"),
    "geopolitical_structural_shifts": ("geopolitics", "energy", "macro"),
    "business_earnings_review": ("business", "markets", "macro"),
    "deep_explainers_synthesis": ("explainer", "macro", "ai"),
    "future_trends_reflection": ("science", "ai", "geopolitics"),
}


def _weekday_index(name: str) -> DayOfWeek:
    mapping = {
        "monday": DayOfWeek.MONDAY,
        "tuesday": DayOfWeek.TUESDAY,
        "wednesday": DayOfWeek.WEDNESDAY,
        "thursday": DayOfWeek.THURSDAY,
        "friday": DayOfWeek.FRIDAY,
        "saturday": DayOfWeek.SATURDAY,
        "sunday": DayOfWeek.SUNDAY,
    }
    return mapping.get(name.lower(), DayOfWeek.MONDAY)


def _time_band(hour: int) -> TimeBand:
    if 6 <= hour < 11:
        return TimeBand.MORNING
    if 11 <= hour < 17:
        return TimeBand.MIDDAY
    return TimeBand.EVENING


def resolve_weekly_experience_slot(
    *,
    weekday_name: str = "monday",
    hour_local: int = 12,
) -> WeeklyExperienceSlot:
    day = _weekday_index(weekday_name)
    band = _time_band(hour_local)
    focus = _WEEKLY_FOCUS[day]
    return WeeklyExperienceSlot(
        day=day,
        time_band=band,
        daily_mode=_TIME_MODE[band],
        cognitive_focus=focus,
        purpose=_TIME_PURPOSE[band],
        preferred_categories=_FOCUS_CATEGORIES.get(focus, ("macro", "markets")),
    )
