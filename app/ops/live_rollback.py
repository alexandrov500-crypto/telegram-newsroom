"""Live rollback mode control (safe freeze, diagnostics preserved)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "live_rollback_state.json"


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def live_rollback_mode_enabled() -> bool:
    return _env_bool("LIVE_ROLLBACK_MODE", "false")


def load_rollback_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return {"active": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"active": False}
    except (OSError, json.JSONDecodeError):
        return {"active": False}


def save_rollback_state(runtime_dir: str, payload: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def activate_live_rollback(runtime_dir: str, *, reason: str, operator_id: int = 0) -> dict[str, Any]:
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st = load_rollback_state(runtime_dir)
    if st.get("active"):
        return st
    payload: dict[str, Any] = {
        "active": True,
        "activated_at": now_iso,
        "activated_unix": time.time(),
        "reason": (reason or "manual").strip()[:300],
        "operator_id": int(operator_id),
    }
    save_rollback_state(runtime_dir, payload)
    try:
        from app.observability.publish_continuity import set_operator_autopublish_pause

        set_operator_autopublish_pause(runtime_dir, paused=True, operator_id=operator_id)
    except Exception:
        pass
    log_event(logger, "live_rollback.activated", reason=payload["reason"], operator_id=operator_id)
    return payload


def deactivate_live_rollback(runtime_dir: str, *, operator_id: int = 0) -> dict[str, Any]:
    st = load_rollback_state(runtime_dir)
    if not st.get("active"):
        return st
    activated_unix = float(st.get("activated_unix") or time.time())
    out = {
        "active": False,
        "deactivated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operator_id": int(operator_id),
        "last_reason": st.get("reason"),
        "last_duration_sec": round(max(0.0, time.time() - activated_unix), 1),
    }
    save_rollback_state(runtime_dir, out)
    log_event(logger, "live_rollback.deactivated", operator_id=operator_id, duration_sec=out["last_duration_sec"])
    return out


def rollback_active(runtime_dir: str | None = None) -> bool:
    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    if not live_rollback_mode_enabled():
        return False
    return bool(load_rollback_state(rd).get("active"))


def rollback_payload(runtime_dir: str) -> dict[str, Any]:
    st = load_rollback_state(runtime_dir)
    if st.get("active"):
        started = float(st.get("activated_unix") or time.time())
        st["duration_sec"] = round(max(0.0, time.time() - started), 1)
    st["enabled"] = live_rollback_mode_enabled()
    st["recovery_workflow"] = [
        "Diagnose root cause from incident + continuity reports",
        "Resolve runtime CRITICAL / publish path blockers",
        "Verify /go_status and /continuity before resume",
        "Operator runs /resume_autopublish when safe",
    ]
    return st


def enforce_live_rollback_if_enabled(runtime_dir: str) -> dict[str, Any]:
    """When LIVE_ROLLBACK_MODE=true, ensure rollback is active and traceable."""
    if not live_rollback_mode_enabled():
        return load_rollback_state(runtime_dir)
    st = load_rollback_state(runtime_dir)
    if st.get("active"):
        return st
    return activate_live_rollback(runtime_dir, reason="LIVE_ROLLBACK_MODE_enabled", operator_id=0)
