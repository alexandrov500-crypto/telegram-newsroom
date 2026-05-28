"""Safe recovery state when execution-graph CRITICAL anomalies fire."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _safety_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "execution_graph_safety.json"


def _load(runtime_dir: str) -> dict[str, Any]:
    path = _safety_path(runtime_dir)
    if not path.is_file():
        return {
            "corrupted_ticks": {},
            "critical_events": [],
            "safe_recovery_active": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"corrupted_ticks": {}, "critical_events": [], "safe_recovery_active": False}


def _save(runtime_dir: str, data: dict[str, Any]) -> None:
    path = _safety_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def activate_safe_recovery(
    runtime_dir: str,
    *,
    tick_id: str,
    critical_codes: list[str],
    terminal_state: str = "",
) -> None:
    """Mark tick corrupted; block publish for tick; persist recovery state (no silent continue)."""
    with _lock:
        data = _load(runtime_dir)
        corrupted = data.setdefault("corrupted_ticks", {})
        corrupted[tick_id] = {
            "critical": critical_codes[:24],
            "terminal_state": terminal_state,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        events = data.setdefault("critical_events", [])
        events.append(
            {
                "tick_id": tick_id,
                "critical": critical_codes[:24],
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        data["critical_events"] = events[-500:]
        data["safe_recovery_active"] = True
        data["last_critical_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save(runtime_dir, data)

    log_event(
        logger,
        "execution_graph.safe_recovery_activated",
        tick_id=tick_id,
        critical_count=len(critical_codes),
        critical_codes=critical_codes[:8],
    )


def is_tick_corrupted(tick_id: str | None, runtime_dir: str | None = None) -> bool:
    if not tick_id:
        return False
    import os

    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    with _lock:
        data = _load(rd)
        return tick_id in (data.get("corrupted_ticks") or {})


def tick_metrics_excluded(tick_id: str | None, runtime_dir: str | None = None) -> bool:
    return is_tick_corrupted(tick_id, runtime_dir)


def critical_count_in_window(runtime_dir: str, *, max_events: int = 500) -> int:
    with _lock:
        data = _load(runtime_dir)
        return len(data.get("critical_events") or [])


def safety_payload(runtime_dir: str) -> dict[str, Any]:
    with _lock:
        data = _load(runtime_dir)
        corrupted = data.get("corrupted_ticks") or {}
        return {
            "safe_recovery_active": bool(data.get("safe_recovery_active")),
            "corrupted_tick_count": len(corrupted),
            "critical_events_total": len(data.get("critical_events") or []),
            "last_critical_at": data.get("last_critical_at"),
        }
