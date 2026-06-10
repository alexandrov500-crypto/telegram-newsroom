"""Anti-pause guarantee — detect publish gaps and active-hours silence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.editorial.desk_starvation import hours_since_last_publish, last_publish_at_sync
from app.editorial.stability.config import (
    active_hours_end,
    active_hours_start,
    anti_pause_gap_minutes,
    anti_pause_max_gap_minutes,
)


@dataclass(frozen=True)
class AntiPauseStatus:
    publish_gap_minutes: float | None
    anti_pause_active: bool
    max_gap_exceeded: bool
    in_active_hours: bool
    hours_since_publish: float | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "publish_gap_minutes": self.publish_gap_minutes,
            "anti_pause_active": self.anti_pause_active,
            "max_gap_exceeded": self.max_gap_exceeded,
            "in_active_hours": self.in_active_hours,
            "hours_since_publish": self.hours_since_publish,
            "reason": self.reason,
        }


def _in_active_hours(now_local: datetime) -> bool:
    h = now_local.hour
    start = active_hours_start()
    end = active_hours_end()
    if start <= end:
        return start <= h < end
    return h >= start or h < end


def evaluate_anti_pause(*, newsroom_tz: str = "Europe/Moscow", now: datetime | None = None) -> AntiPauseStatus:
    try:
        tz = ZoneInfo(newsroom_tz)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    active = _in_active_hours(now_local)

    hrs = hours_since_last_publish()
    gap_min = (hrs * 60.0) if hrs is not None else None
    trigger = float(anti_pause_gap_minutes())
    max_gap = float(anti_pause_max_gap_minutes())

    if not active:
        return AntiPauseStatus(
            publish_gap_minutes=gap_min,
            anti_pause_active=False,
            max_gap_exceeded=False,
            in_active_hours=False,
            hours_since_publish=round(hrs, 2) if hrs is not None else None,
            reason="offhours",
        )

    if gap_min is None:
        return AntiPauseStatus(
            publish_gap_minutes=None,
            anti_pause_active=True,
            max_gap_exceeded=True,
            in_active_hours=True,
            hours_since_publish=None,
            reason="never_published",
        )

    anti = gap_min >= trigger
    max_exceeded = gap_min >= max_gap
    reason = "gap_ok"
    if max_exceeded:
        reason = "max_gap_exceeded"
    elif anti:
        reason = "anti_pause_triggered"

    return AntiPauseStatus(
        publish_gap_minutes=round(gap_min, 1),
        anti_pause_active=anti,
        max_gap_exceeded=max_exceeded,
        in_active_hours=True,
        hours_since_publish=round(hrs, 2) if hrs is not None else None,
        reason=reason,
    )


def record_silence_event(runtime_dir: str | None, *, reason: str, gap_minutes: float | None) -> None:
    from app.editorial.stability.state import load_state, save_state

    data = load_state(runtime_dir)
    events = list(data.get("silence_events") or [])
    events.append(
        {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": reason[:120],
            "gap_minutes": gap_minutes,
        }
    )
    data["silence_events"] = events[-100:]
    save_state(runtime_dir, data)
