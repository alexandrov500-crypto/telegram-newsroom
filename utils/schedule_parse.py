from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    pass


def _combine_local(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def parse_draft_schedule_at(
    raw: str,
    *,
    now: datetime,
    tz_name: str,
) -> datetime | None:
    """
    Parse schedule string into timezone-aware UTC datetime.
    Supports:
    - HH:MM (today or next calendar day in tz if already passed)
    - YYYY-MM-DDTHH:MM:SS (optional trailing Z for UTC)
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    if not now.tzinfo:
        now = now.replace(tzinfo=ZoneInfo("UTC"))

    now_local = now.astimezone(tz)

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?", s):
        iso = s[:-1] + "+00:00" if s.endswith("Z") else s
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    t = time(hour=hh, minute=mm, tzinfo=tz)
    today_local = _combine_local(now_local.date(), t, tz)
    if today_local <= now_local:
        today_local = _combine_local(now_local.date() + timedelta(days=1), t, tz)
    return today_local.astimezone(ZoneInfo("UTC"))
