"""Public incident safety — freeze autonomous publish on CRITICAL runtime events."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)

_NOTIFY_COOLDOWN_SEC = 1800.0
_RESTART_LOOP_WINDOW_SEC = 1800.0
_RESTART_LOOP_MAX_CRITICAL = 2


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "public_incident_state.json"


def _diagnostics_dir(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "incident_diagnostics"


def _default_state() -> dict[str, Any]:
    return {
        "frozen": False,
        "frozen_at": None,
        "reasons": [],
        "last_notified_at": None,
        "critical_events": [],
        "restart_loop_guard_until": None,
        "diagnostics_paths": [],
    }


def load_incident_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def save_incident_state(runtime_dir: str, state: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def incident_frozen(runtime_dir: str | None = None) -> bool:
    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    st = load_incident_state(rd)
    if not st.get("frozen"):
        return False
    guard_until = st.get("restart_loop_guard_until")
    if guard_until:
        try:
            if time.time() < float(guard_until):
                return True
        except (TypeError, ValueError):
            pass
    return bool(st.get("frozen"))


def restart_loop_guard_active(runtime_dir: str) -> bool:
    st = load_incident_state(runtime_dir)
    until = st.get("restart_loop_guard_until")
    if not until:
        return False
    try:
        return time.time() < float(until)
    except (TypeError, ValueError):
        return False


def _prune_critical_events(events: list[dict[str, Any]], *, window_sec: float) -> list[dict[str, Any]]:
    cutoff = time.time() - window_sec
    out: list[dict[str, Any]] = []
    for ev in events:
        try:
            if float(ev.get("at_unix") or 0) >= cutoff:
                out.append(ev)
        except (TypeError, ValueError):
            continue
    return out[-20:]


def preserve_incident_diagnostics(runtime_dir: str, *, snapshot: dict[str, Any], reasons: list[str]) -> str | None:
    diag_dir = _diagnostics_dir(runtime_dir)
    diag_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = diag_dir / f"critical_{stamp}.json"
    payload = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reasons": reasons[:24],
        "protection_snapshot": snapshot,
    }
    try:
        from app.observability.publish_continuity import compute_autonomous_continuity_score
        from utils.database_url import sqlite_path_from_url

        db_raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
        db_path = sqlite_path_from_url(db_raw)
        if db_path and Path(db_path).is_file():
            import sqlite3

            conn = sqlite3.connect(db_path, timeout=5.0)
            try:
                payload["continuity"] = compute_autonomous_continuity_score(conn, runtime_dir=runtime_dir)
            finally:
                conn.close()
    except Exception as exc:
        payload["continuity_error"] = repr(exc)[:200]
    try:
        from app.runtime_activity import activity_snapshot

        payload["activity"] = activity_snapshot()
    except Exception:
        pass
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(path)
    except OSError as exc:
        log_event(logger, "public_incident.diagnostics_failed", error=repr(exc)[:120])
        return None


def _notify_operator(runtime_dir: str, *, message: str, fields: dict[str, Any]) -> None:
    st = load_incident_state(runtime_dir)
    last = st.get("last_notified_at")
    if last:
        try:
            if time.time() - float(last) < _NOTIFY_COOLDOWN_SEC:
                return
        except (TypeError, ValueError):
            pass
    try:
        from ops.operator_notifications import enqueue_operator_notification

        enqueue_operator_notification(
            runtime_dir,
            kind="public_incident_critical",
            severity="critical",
            message=message[:400],
            fields=fields,
        )
        st["last_notified_at"] = time.time()
        save_incident_state(runtime_dir, st)
    except Exception as exc:
        log_event(logger, "public_incident.notify_failed", error=repr(exc)[:120])


def on_runtime_critical(
    runtime_dir: str,
    *,
    reasons: list[str],
    protection_snapshot: dict[str, Any] | None = None,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Activate incident freeze, preserve diagnostics, notify operator."""
    st = load_incident_state(runtime_dir)
    now = time.time()
    events = _prune_critical_events(list(st.get("critical_events") or []), window_sec=_RESTART_LOOP_WINDOW_SEC)
    events.append({"at_unix": now, "reasons": reasons[:12]})
    st["critical_events"] = events

    critical_in_window = len(events)
    if critical_in_window >= _RESTART_LOOP_MAX_CRITICAL:
        guard_sec = float(os.getenv("PUBLIC_INCIDENT_RESTART_GUARD_SEC", "3600"))
        st["restart_loop_guard_until"] = now + guard_sec
        log_event(
            logger,
            "public_incident.restart_loop_guard",
            critical_count=critical_in_window,
            guard_sec=guard_sec,
        )

    st["frozen"] = True
    st["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st["reasons"] = reasons[:24]

    snap = protection_snapshot or {}
    diag_path = preserve_incident_diagnostics(runtime_dir, snapshot=snap, reasons=reasons)
    if diag_path:
        paths = list(st.get("diagnostics_paths") or [])
        paths.append(diag_path)
        st["diagnostics_paths"] = paths[-10:]

    save_incident_state(runtime_dir, st)

    try:
        from app.observability.publish_continuity import set_operator_autopublish_pause

        set_operator_autopublish_pause(runtime_dir, paused=True, operator_id=0)
    except Exception as exc:
        log_event(logger, "public_incident.autopublish_pause_failed", error=repr(exc)[:120])

    _notify_operator(
        runtime_dir,
        message=(
            "Public incident safety: runtime CRITICAL — autonomous publish frozen.\n"
            f"Reasons: {', '.join(reasons[:6])}\n"
            "Resolve degradation before /resume_autopublish."
        ),
        fields={"reasons": reasons[:12], "diagnostics": diag_path, "frozen_at": st["frozen_at"]},
    )
    log_event(logger, "public_incident.frozen", reasons=reasons[:8], diagnostics=diag_path)
    return st


def clear_incident_freeze(runtime_dir: str, *, operator_id: int = 0) -> None:
    st = load_incident_state(runtime_dir)
    st["frozen"] = False
    st["frozen_at"] = None
    st["reasons"] = []
    save_incident_state(runtime_dir, st)
    try:
        from app.observability.publish_continuity import set_operator_autopublish_pause

        set_operator_autopublish_pause(runtime_dir, paused=False, operator_id=operator_id)
    except Exception:
        pass
    log_event(logger, "public_incident.cleared", operator_id=operator_id)


def evaluate_incident_safety(runtime_dir: str, *, settings: Any | None = None) -> dict[str, Any]:
    """Heartbeat hook — sync with runtime protection CRITICAL state."""
    from app.observability.runtime_protection import RuntimeHealthLevel, current_protection_level, protection_payload

    level = current_protection_level(runtime_dir)
    st = load_incident_state(runtime_dir)
    if level == RuntimeHealthLevel.CRITICAL and not st.get("frozen"):
        st = on_runtime_critical(
            runtime_dir,
            reasons=list(protection_payload(runtime_dir).get("active_protections") or ["runtime_critical"]),
            protection_snapshot=protection_payload(runtime_dir),
            settings=settings,
        )
    return {
        "incident_frozen": bool(st.get("frozen")),
        "restart_loop_guard": restart_loop_guard_active(runtime_dir),
        "runtime_level": level.value,
        "state": st,
    }


def incident_payload(runtime_dir: str) -> dict[str, Any]:
    st = load_incident_state(runtime_dir)
    return {
        "frozen": bool(st.get("frozen")),
        "frozen_at": st.get("frozen_at"),
        "reasons": st.get("reasons"),
        "restart_loop_guard_active": restart_loop_guard_active(runtime_dir),
        "diagnostics_count": len(st.get("diagnostics_paths") or []),
    }
