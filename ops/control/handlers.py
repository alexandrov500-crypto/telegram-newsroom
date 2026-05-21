"""Operator control actions (audited, safe concurrency)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.operational_mode import OperationalMode, load_operational_mode, set_operational_mode
from ops.control.journal import append_control_action
from ops.resilience.leadership import get_leadership
from ops.resilience.snapshot import create_snapshot, list_snapshots


def _ok(action: str, correlation_id: str, runtime_dir: str, detail: dict[str, Any]) -> dict[str, Any]:
    entry = append_control_action(
        runtime_dir,
        action=action,
        outcome="ok",
        correlation_id=correlation_id,
        detail=detail,
    )
    return {"ok": True, "correlation_id": correlation_id, "action_id": entry["id"], "detail": detail}


def _err(action: str, correlation_id: str, runtime_dir: str, message: str) -> dict[str, Any]:
    append_control_action(
        runtime_dir,
        action=action,
        outcome="error",
        correlation_id=correlation_id,
        detail={"error": message[:300]},
    )
    return {"ok": False, "correlation_id": correlation_id, "error": message}


def handle_set_mode(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    raw = str(body.get("mode") or "").strip().lower()
    reason = str(body.get("reason") or "operator_api")[:200]
    try:
        mode = OperationalMode(raw)
    except ValueError:
        return _err("mode.set", correlation_id, settings.runtime_state_dir, f"invalid mode: {raw}")
    set_operational_mode(settings.runtime_state_dir, mode, reason=reason)
    from ops.operator_notifications import enqueue_operator_notification

    enqueue_operator_notification(
        settings.runtime_state_dir,
        kind="operational_mode_changed",
        severity="info",
        message=f"Operational mode set to {mode.value}",
        fields={"mode": mode.value, "reason": reason},
    )
    return _ok("mode.set", correlation_id, settings.runtime_state_dir, {"mode": mode.value, "reason": reason})


def handle_maintenance(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    reason = str(body.get("reason") or "maintenance")[:200]
    set_operational_mode(settings.runtime_state_dir, OperationalMode.MAINTENANCE, reason=reason)
    return _ok("maintenance.enable", correlation_id, settings.runtime_state_dir, {"mode": "maintenance"})


def handle_recovery_mode(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    reason = str(body.get("reason") or "recovery")[:200]
    set_operational_mode(settings.runtime_state_dir, OperationalMode.RECOVERY, reason=reason)
    return _ok("recovery.enable", correlation_id, settings.runtime_state_dir, {"mode": "recovery"})


def handle_snapshot(settings: Any, _body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    try:
        path = create_snapshot(
            runtime_dir=settings.runtime_state_dir,
            database_url=settings.database_url,
            extra_metadata={"trigger": "operator_control", "correlation_id": correlation_id},
        )
        return _ok("snapshot.create", correlation_id, settings.runtime_state_dir, {"path": str(path)})
    except Exception as exc:
        from ops.operator_notifications import enqueue_operator_notification

        enqueue_operator_notification(
            settings.runtime_state_dir,
            kind="snapshot_failed",
            severity="high",
            message=f"Snapshot failed: {exc!s}"[:200],
        )
        return _err("snapshot.create", correlation_id, settings.runtime_state_dir, repr(exc))


def handle_clear_locks(settings: Any, _body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    locks = Path(settings.runtime_state_dir) / "locks"
    removed: list[str] = []
    if locks.is_dir():
        for p in locks.glob("*.lock"):
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                pass
    coord = get_leadership(settings.runtime_state_dir)
    from app.runtime_lifecycle import runtime_id

    reacquired = coord.acquire_all(runtime_id=runtime_id())
    return _ok(
        "locks.clear",
        correlation_id,
        settings.runtime_state_dir,
        {"removed": removed, "reacquired": reacquired},
    )


def handle_source_mute(settings: Any, body: dict[str, Any], correlation_id: str, *, unmute: bool) -> dict[str, Any]:
    ch = str(body.get("channel") or "").strip()
    if not ch:
        return _err("source.mute", correlation_id, settings.runtime_state_dir, "channel required")
    from editorial.governance.operator_controls import mute_source

    if unmute:
        data_path = Path(settings.runtime_state_dir) / "editorial" / "operator_controls.json"
        if data_path.is_file():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
                mutes = dict(data.get("source_mutes") or {})
                mutes.pop(ch.lower(), None)
                data["source_mutes"] = mutes
                data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except (OSError, json.JSONDecodeError):
                pass
        action = "source.unmute"
    else:
        mins = float(body.get("minutes") or 60.0)
        mute_source(settings.runtime_state_dir, ch, ttl_sec=mins * 60.0, reason="ops_control_api")
        action = "source.mute"
    return _ok(action, correlation_id, settings.runtime_state_dir, {"channel": ch})


def handle_editorial_freeze(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    from editorial.governance.operator_controls import set_emergency_freeze

    enabled = body.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("1", "true", "yes", "on")
    reason = str(body.get("reason") or "ops_control")[:200]
    set_emergency_freeze(settings.runtime_state_dir, enabled=bool(enabled), reason=reason)
    action = "editorial.freeze" if enabled else "editorial.unfreeze"
    return _ok(action, correlation_id, settings.runtime_state_dir, {"enabled": bool(enabled)})


def handle_leadership_rotate(settings: Any, _body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    from app.runtime_lifecycle import runtime_id

    coord = get_leadership(settings.runtime_state_dir)
    coord.release_all()
    acquired = coord.acquire_all(runtime_id=runtime_id())
    return _ok("leadership.rotate", correlation_id, settings.runtime_state_dir, {"acquired": acquired})


def handle_replay(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Non-destructive recovery drill + transparency export metadata."""
    from tools.recovery_drill import run_drill

    out = Path(settings.runtime_state_dir) / "recovery_drill_report.json"
    report = run_drill(settings.runtime_state_dir, out)
    hours = float(body.get("hours") or 24.0)
    from ops.transparency.export import build_transparency_bundle

    bundle = build_transparency_bundle(settings, hours=hours)
    return _ok(
        "replay.trigger",
        correlation_id,
        settings.runtime_state_dir,
        {"drill_risk": report.get("overall_risk"), "transparency_keys": list(bundle.keys())},
    )


def handle_economic_mode(settings: Any, body: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    from ops.economics.economic_mode import EconomicMode, set_economic_mode

    raw = str(body.get("mode") or "balanced").strip().lower()
    try:
        mode = EconomicMode(raw)
    except ValueError:
        return _err("economic.mode", correlation_id, settings.runtime_state_dir, f"invalid: {raw}")
    set_economic_mode(settings.runtime_state_dir, mode, reason=str(body.get("reason") or "ops_control"))
    return _ok("economic.mode", correlation_id, settings.runtime_state_dir, {"mode": mode.value})


def dispatch_control_action(
    settings: Any,
    subpath: str,
    body: dict[str, Any],
    *,
    correlation_id: str,
) -> dict[str, Any]:
    p = subpath.strip("/").lower()
    if p in ("mode", "mode/set"):
        return handle_set_mode(settings, body, correlation_id)
    if p in ("maintenance", "maintenance/on"):
        return handle_maintenance(settings, body, correlation_id)
    if p in ("recovery", "recovery/on"):
        return handle_recovery_mode(settings, body, correlation_id)
    if p in ("snapshot", "snapshot/create"):
        return handle_snapshot(settings, body, correlation_id)
    if p in ("locks/clear", "locks"):
        return handle_clear_locks(settings, body, correlation_id)
    if p in ("source/mute",):
        return handle_source_mute(settings, body, correlation_id, unmute=False)
    if p in ("source/unmute",):
        return handle_source_mute(settings, body, correlation_id, unmute=True)
    if p in ("editorial/freeze",):
        body = {**body, "enabled": True}
        return handle_editorial_freeze(settings, body, correlation_id)
    if p in ("editorial/unfreeze",):
        body = {**body, "enabled": False}
        return handle_editorial_freeze(settings, body, correlation_id)
    if p in ("leadership/rotate", "leadership"):
        return handle_leadership_rotate(settings, body, correlation_id)
    if p in ("replay", "replay/trigger"):
        return handle_replay(settings, body, correlation_id)
    if p in ("economic/mode", "economic"):
        return handle_economic_mode(settings, body, correlation_id)
    if p == "status":
        return {
            "ok": True,
            "correlation_id": correlation_id,
            "mode": load_operational_mode(settings.runtime_state_dir, settings).value,
            "snapshots": list_snapshots(settings.runtime_state_dir)[:5],
        }
    return _err("unknown", correlation_id, settings.runtime_state_dir, f"unknown control path: {p}")
