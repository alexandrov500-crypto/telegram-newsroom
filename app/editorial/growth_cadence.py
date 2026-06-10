"""Growth cadence layer: predictable sessions, caps, and signature formats."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CadenceSession:
    key: str
    signature: str
    max_items: int
    min_priority_score: float


_SESSIONS: dict[str, CadenceSession] = {
    "morning_briefing": CadenceSession(
        key="morning_briefing",
        signature="5-Minute Macro",
        max_items=2,
        min_priority_score=56.0,
    ),
    "intraday_signals": CadenceSession(
        key="intraday_signals",
        signature="Market Pulse",
        max_items=4,
        min_priority_score=62.0,
    ),
    "evening_recap": CadenceSession(
        key="evening_recap",
        signature="Closing Bell",
        max_items=2,
        min_priority_score=58.0,
    ),
    "offhours": CadenceSession(
        key="offhours",
        signature="Alpha Flow",
        max_items=1,
        min_priority_score=76.0,
    ),
}


def _state_path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    return base / "growth_cadence_state.json"


def _today_key(now_local: datetime) -> str:
    return now_local.strftime("%Y-%m-%d")


def _session_for_hour(hour: int) -> CadenceSession:
    if 8 <= hour < 10:
        return _SESSIONS["morning_briefing"]
    if 10 <= hour < 19:
        return _SESSIONS["intraday_signals"]
    if 19 <= hour < 22:
        return _SESSIONS["evening_recap"]
    return _SESSIONS["offhours"]


def _daily_cap() -> int:
    try:
        return max(6, min(50, int(os.getenv("GROWTH_CADENCE_DAILY_CAP", "20"))))
    except ValueError:
        return 20


def now_in_newsroom_tz(newsroom_tz: str | None = None) -> datetime:
    tz_name = (newsroom_tz or os.getenv("NEWSROOM_TIMEZONE", "Europe/Moscow")).strip() or "Europe/Moscow"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    return datetime.now(UTC).astimezone(tz)


def resolve_cadence_session(*, now_local: datetime | None = None, newsroom_tz: str | None = None) -> CadenceSession:
    n = now_local or now_in_newsroom_tz(newsroom_tz)
    return _session_for_hour(n.hour)


def signature_line_for_now(*, now_local: datetime | None = None, newsroom_tz: str | None = None) -> str:
    # Off by default: the English column labels ("Alpha Flow", "Market Pulse"…)
    # appeared as a bare line above the headline and confused readers.
    if os.getenv("GROWTH_SIGNATURE_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return ""
    return resolve_cadence_session(now_local=now_local, newsroom_tz=newsroom_tz).signature


def allow_story_for_current_session(
    *,
    runtime_dir: str | None,
    priority_score: float,
    is_breaking: bool,
    newsroom_tz: str | None = None,
    now_local: datetime | None = None,
) -> tuple[bool, str, CadenceSession]:
    now_ref = now_local or now_in_newsroom_tz(newsroom_tz)
    session = resolve_cadence_session(now_local=now_ref, newsroom_tz=newsroom_tz)
    if is_breaking:
        return True, "breaking_immediate", session

    min_priority = session.min_priority_score
    max_items = session.max_items
    try:
        from app.editorial.ai_editorial_reviewer import autonomous_editorial_mode_enabled

        if autonomous_editorial_mode_enabled():
            min_priority = max(48.0, min_priority - 12.0)
            max_items = max_items + 2
    except Exception:
        pass

    try:
        from app.editorial.desk_starvation import desk_threshold_context

        ctx = desk_threshold_context()
        if ctx.publish_starvation_detected:
            min_priority = min(min_priority, float(ctx.effective_threshold))
    except Exception:
        pass

    if priority_score < min_priority:
        return False, "below_session_priority_threshold", session

    p = _state_path(runtime_dir)
    date_key = _today_key(now_ref)
    state: dict[str, object] = {}
    if p.is_file():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}

    days = state.get("days")
    if not isinstance(days, dict):
        days = {}
    today = days.get(date_key)
    if not isinstance(today, dict):
        today = {}
    total = int(today.get("total") or 0)
    sess_counts = today.get("sessions")
    if not isinstance(sess_counts, dict):
        sess_counts = {}
    cur_count = int(sess_counts.get(session.key) or 0)

    if total >= _daily_cap():
        return False, "daily_cap_reached", session
    if cur_count >= max_items:
        return False, "session_cap_reached", session

    sess_counts[session.key] = cur_count + 1
    today["sessions"] = sess_counts
    today["total"] = total + 1
    days[date_key] = today
    state["days"] = days
    state["last_updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, "allowed", session
