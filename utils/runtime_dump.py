from __future__ import annotations

import json
from dataclasses import fields
from typing import Any

from app.config import Settings
from utils.diagnostics import process_uptime_sec
from utils.metrics import export_snapshot
from utils.observability import export_tick_timing_statistics, get_runtime_snapshot
from utils.runtime_events import get_recent_runtime_events


def sanitize_settings_for_dump(settings: Settings) -> dict[str, Any]:
    """Dataclass as dict with secrets redacted (JSON-serializable)."""
    raw = {f.name: getattr(settings, f.name) for f in fields(settings)}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in {"openai_api_key", "telegram_api_hash", "telethon_session_string"}:
            out[k] = "<redacted>" if v else None
        elif k == "bot_token":
            if isinstance(v, str) and ":" in v:
                pre, _, suf = v.partition(":")
                out[k] = f"{pre}:***"
            else:
                out[k] = "<redacted>"
        elif k == "database_url" and isinstance(v, str):
            try:
                from sqlalchemy.engine import make_url

                u = make_url(v)
                tail = (u.database or "db").split("/")[-1][:48]
                out[k] = f"{u.get_driver_name()}://***/{tail}"
            except Exception:
                out[k] = "<database_url>"
        else:
            out[k] = v
    return out


def _pipeline_lock_status() -> dict[str, Any]:
    try:
        from scheduler.pipeline_lock import get_pipeline_lock

        lock = get_pipeline_lock()
        return {"pipeline_lock_locked": bool(lock.locked())}
    except Exception as exc:
        return {"pipeline_lock_locked": None, "pipeline_lock_error": str(exc)}


def generate_runtime_dump(settings: Settings, *, events_limit: int = 64) -> dict[str, Any]:
    """
    Operational diagnostics bundle: snapshots + sanitized config (no network).
    """
    snap = get_runtime_snapshot(settings)
    metrics = export_snapshot()
    events = get_recent_runtime_events(events_limit)
    tick_stats = export_tick_timing_statistics()
    return {
        "schema_version": 1,
        "uptime_sec": round(process_uptime_sec(), 4),
        "runtime_snapshot": snap,
        "metrics": metrics,
        "scheduler_state": snap.get("scheduler", {}),
        "active_locks": _pipeline_lock_status(),
        "tick_statistics": tick_stats,
        "recent_runtime_events": events,
        "sanitized_settings": sanitize_settings_for_dump(settings),
    }


def runtime_dump_json(settings: Settings, *, events_limit: int = 64) -> str:
    return json.dumps(generate_runtime_dump(settings, events_limit=events_limit), default=str)
