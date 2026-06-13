"""Peak-hour publishing — bias cadence toward audience-active windows (MSK default)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


def peak_hour_mode() -> str:
    """off | soft | strict — soft adjusts scores/intervals; strict can defer non-breaking."""
    raw = os.getenv("GROWTH_PEAK_HOUR_MODE", "soft").strip().lower()
    return raw if raw in {"off", "soft", "strict"} else "soft"


def peak_hour_window() -> tuple[int, int]:
    try:
        start = int(os.getenv("GROWTH_PEAK_HOUR_START", "10"))
        end = int(os.getenv("GROWTH_PEAK_HOUR_END", "18"))
    except ValueError:
        start, end = 10, 18
    return max(0, min(23, start)), max(1, min(24, end))


@dataclass(frozen=True)
class PeakHourVerdict:
    in_peak: bool
    score_multiplier: float
    interval_multiplier: float
    defer: bool
    reason: str


def _in_window(hour: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def evaluate_peak_hour(
    *,
    hour_local: int,
    is_breaking: bool = False,
    newsroom_tz: str = "Europe/Moscow",
) -> PeakHourVerdict:
    _ = newsroom_tz
    mode = peak_hour_mode()
    if mode == "off" or is_breaking:
        return PeakHourVerdict(True, 1.0, 1.0, False, "breaking_or_off")

    start, end = peak_hour_window()
    in_peak = _in_window(int(hour_local) % 24, start, end)

    if in_peak:
        return PeakHourVerdict(True, 1.12, 0.88, False, "peak_window")

    if mode == "soft":
        return PeakHourVerdict(False, 0.92, 1.15, False, "off_peak_soft")

    return PeakHourVerdict(False, 0.85, 1.35, True, "off_peak_strict")


def current_peak_verdict(*, newsroom_tz: str = "Europe/Moscow", is_breaking: bool = False) -> PeakHourVerdict:
    try:
        hour = datetime.now(ZoneInfo(newsroom_tz)).hour
    except Exception:
        hour = 12
    return evaluate_peak_hour(hour_local=hour, is_breaking=is_breaking, newsroom_tz=newsroom_tz)
