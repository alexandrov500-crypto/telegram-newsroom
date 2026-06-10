"""OSGCP persistent state."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "osgcp_state.json"


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "days": {}, "attention_buffer": [], "desk_rejects_streak": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "days": {}, "attention_buffer": [], "desk_rejects_streak": 0}


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_osgcp_decision(
    runtime_dir: str | None,
    *,
    editorial_state: str,
    action: str,
    format_mode: str,
    continuity_triggered: bool = False,
    published: bool = False,
) -> None:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    days = dict(data.get("days") or {})
    day = dict(days.get(day_key) or {})

    states = dict(day.get("state_counts") or {})
    states[editorial_state] = int(states.get(editorial_state) or 0) + 1
    day["state_counts"] = states

    actions = dict(day.get("action_counts") or {})
    actions[action] = int(actions.get(action) or 0) + 1
    day["action_counts"] = actions

    fm = dict(day.get("format_mode_counts") or {})
    fm[format_mode] = int(fm.get(format_mode) or 0) + 1
    day["format_mode_counts"] = fm

    day["evaluated"] = int(day.get("evaluated") or 0) + 1
    if continuity_triggered:
        day["continuity_triggers"] = int(day.get("continuity_triggers") or 0) + 1
    if published:
        day["published"] = int(day.get("published") or 0) + 1

    days[day_key] = day
    data["days"] = days
    save_state(runtime_dir, data)


def osgcp_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    return {
        "evaluated_today": int(day.get("evaluated") or 0),
        "published_today": int(day.get("published") or 0),
        "state_distribution": dict(day.get("state_counts") or {}),
        "action_distribution": dict(day.get("action_counts") or {}),
        "format_mode_distribution": dict(day.get("format_mode_counts") or {}),
        "continuity_triggers_today": int(day.get("continuity_triggers") or 0),
        "attention_buffer_size": len(data.get("attention_buffer") or []),
        "desk_rejects_streak": int(data.get("desk_rejects_streak") or 0),
        "objective": "adaptive_cognitive_information_os_continuous_flow",
    }
