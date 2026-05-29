"""Retention habit loop — morning / midday / evening anchors."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class HabitSlot:
    key: str
    label: str
    hour_start: int
    hour_end: int
    cadence_boost: float
    anticipation_hook: str


HABIT_SLOTS: tuple[HabitSlot, ...] = (
    HabitSlot("morning_anchor", "Morning Brief", 7, 10, 1.08, "Открытие сессии — ключевые сигналы:"),
    HabitSlot("midday_pulse", "Midday Signal", 12, 14, 1.05, "Пульс дня:"),
    HabitSlot("evening_closure", "Evening Recap", 18, 21, 1.06, "Итоги и контекст:"),
    HabitSlot("weekly_synthesis", "Weekly Arc", 10, 12, 1.1, "Недельная арка:"),
)


def active_habit_slot(newsroom_tz: str = "Europe/Moscow") -> HabitSlot | None:
    if os.getenv("RETENTION_HABIT_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        now = datetime.now(ZoneInfo(newsroom_tz))
    except Exception:
        now = datetime.now(UTC)
    h, wd = now.hour, now.weekday()
    for slot in HABIT_SLOTS:
        if slot.key == "weekly_synthesis" and wd != 6:
            continue
        if slot.hour_start <= h < slot.hour_end:
            return slot
    return None


def record_habit_touch(runtime_dir: str, slot_key: str) -> None:
    p = Path(runtime_dir) / "retention_habit_state.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"touches": {}}
    touches: dict = dict(data.get("touches") or {})
    touches[slot_key] = datetime.now(UTC).isoformat()
    data["touches"] = touches
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
