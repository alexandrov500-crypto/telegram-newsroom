from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from utils.runtime_dump import generate_runtime_dump
from utils.runtime_events import get_recent_runtime_events
from utils.runtime_retention import cleanup_old_runtime_snapshots as _retention_cleanup_snapshots
from utils.runtime_retention import list_snapshot_files
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_LATEST_NAME = "_latest_snapshot.txt"
_SNAPSHOT_PREFIX = "snapshot_"
_lock = threading.Lock()
_last_event_flush_mono: float | None = None


def _wall_mono() -> float:
    return time.monotonic()


def _slug_reason(reason: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", reason.strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:56] or "unknown")


def snapshot_dir(settings: Settings) -> Path:
    return Path(settings.runtime_state_dir).expanduser().resolve()


def _recent_errors_from_dump(dump: dict[str, Any], *, limit: int = 32) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in dump.get("recent_runtime_events") or []:
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get("kind", "")).lower()
        msg = str(ev.get("message", "")).lower()
        if "fail" in kind or "fail" in msg or "error" in kind:
            out.append(dict(ev))
    return out[-limit:]


def save_runtime_snapshot(settings: Settings, reason: str, *, events_limit: int = 96) -> Path:
    """
    Persist a JSON record (atomic write). Secrets must already be redacted in dump payloads.
    """
    directory = snapshot_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)

    dump = generate_runtime_dump(settings, events_limit=events_limit)
    rs = dump.get("runtime_snapshot") or {}
    metrics = dump.get("metrics") or {}
    sched = rs.get("scheduler") or {}

    record: dict[str, Any] = {
        "schema_version": 2,
        "recorded_at_unix": time.time(),
        "recorded_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason,
        "runtime_snapshot": rs,
        "metrics": metrics,
        "diagnostics_dump": dump,
        "scheduler_state": sched,
        "recent_errors": _recent_errors_from_dump(dump),
        "recent_runtime_events_tail": dump.get("recent_runtime_events") or [],
    }

    ms = int(time.time() * 1000)
    final_name = f"{_SNAPSHOT_PREFIX}{ms}_{_slug_reason(reason)}.json"
    final_path = directory / final_name
    tmp_path = directory / (final_name + ".tmp")

    payload = json.dumps(record, ensure_ascii=False, default=str, indent=2)
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(final_path)

    latest = directory / _LATEST_NAME
    latest_tmp = directory / (_LATEST_NAME + ".tmp")
    latest_tmp.write_text(final_name, encoding="utf-8")
    latest_tmp.replace(latest)

    log_event(logger, "runtime.snapshot_saved", path=final_name, reason=reason)
    return final_path


def try_save_runtime_snapshot(settings: Settings, reason: str, *, events_limit: int = 96) -> None:
    """Never raises: snapshot persistence must not take down the process."""
    try:
        save_runtime_snapshot(settings, reason, events_limit=events_limit)
        _retention_cleanup_snapshots(settings)
    except Exception as exc:
        log_event(logger, "runtime.snapshot_persist_failed", error=repr(exc), reason=reason, recovery="ignored")


def load_latest_runtime_snapshot(settings: Settings) -> dict[str, Any] | None:
    """Load newest readable snapshot, skipping corrupt files."""
    directory = snapshot_dir(settings)
    if not directory.is_dir():
        return None

    paths = sorted(
        list_snapshot_files(directory),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("schema_version"):
                return data
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
    return None


def maybe_flush_runtime_events_to_snapshot(settings: Settings) -> None:
    """Periodic lightweight persistence of recent events + full dump (throttled)."""
    global _last_event_flush_mono
    interval = max(60, int(settings.runtime_event_flush_interval_sec))
    now = _wall_mono()
    with _lock:
        if _last_event_flush_mono is not None and (now - _last_event_flush_mono) < interval:
            return
        _last_event_flush_mono = now
    try_save_runtime_snapshot(settings, "periodic_events_flush", events_limit=160)


def reset_runtime_flush_clock_for_tests() -> None:
    global _last_event_flush_mono
    with _lock:
        _last_event_flush_mono = None


def cleanup_old_runtime_snapshots(settings: Settings) -> int:
    """Bounded retention for JSON snapshots (delegates to ``runtime_retention``)."""
    return _retention_cleanup_snapshots(settings)
