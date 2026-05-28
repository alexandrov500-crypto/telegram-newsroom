"""Automatic maintenance mode triggers (publish pauses, drafts continue)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.operational_mode import OperationalMode, load_operational_mode, set_operational_mode
from ops.operator_notifications import enqueue_operator_notification
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _state_path(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "auto_maintenance.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def auto_maintenance_snapshot(runtime_dir: str) -> dict[str, Any]:
    p = _state_path(runtime_dir)
    if not p.is_file():
        return {"active": False, "reason": "", "triggered_at_unix": 0.0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"active": False}
    except (OSError, json.JSONDecodeError):
        return {"active": False}


def publish_halted(runtime_dir: str) -> bool:
    return bool(auto_maintenance_snapshot(runtime_dir).get("active"))


def enable_auto_maintenance(runtime_dir: str, *, reason: str) -> None:
    snap = {"active": True, "reason": reason[:300], "triggered_at_unix": time.time(), "publish_halted": True}
    _state_path(runtime_dir).write_text(json.dumps(snap, indent=2), encoding="utf-8")
    set_operational_mode(runtime_dir, OperationalMode.DEGRADED, reason=f"auto:{reason[:120]}")
    enqueue_operator_notification(
        runtime_dir,
        kind="auto_maintenance_on",
        severity="high",
        message=f"Maintenance mode (auto): {reason[:200]}",
        fields={"reason": reason[:200]},
    )
    log_event(logger, "auto_maintenance.enabled", reason=reason[:200])


def disable_auto_maintenance(runtime_dir: str, *, reason: str = "operator_clear") -> None:
    p = _state_path(runtime_dir)
    if p.is_file():
        p.unlink()
    set_operational_mode(runtime_dir, OperationalMode.PRODUCTION, reason=reason[:120])
    log_event(logger, "auto_maintenance.cleared", reason=reason[:120])
    log_event(logger, "auto_maintenance.disabled", reason=reason[:120])


async def evaluate_auto_maintenance(settings: Any) -> dict[str, Any]:
    """Evaluate triggers; enter maintenance when thresholds exceeded."""
    from app.openai_circuit import get_openai_circuit
    from app.dependency_state import get_dependency_state
    from db.reliability_repository import list_due_failed_drafts

    rd = settings.runtime_state_dir
    triggers: list[str] = []

    deps = get_dependency_state()
    if deps.conflict_detected:
        triggers.append("telegram_polling_conflict")

    circuit = get_openai_circuit().snapshot()
    if circuit.get("state") == "open":
        triggers.append("openai_circuit_open")

    if deps.database.status.value == "unavailable":
        triggers.append("database_unavailable")

    try:
        from utils.metrics import export_snapshot

        gauges = (export_snapshot().get("gauges") or {})
        depth = int(gauges.get("queue_depth", 0) or 0)
        warn = int(getattr(settings, "runtime_queue_pending_warn", 64) or 64)
        if depth >= warn * 2:
            triggers.append("queue_congestion")
    except Exception:
        pass

    failed_due = await list_due_failed_drafts(limit=32)
    if len(failed_due) >= 6:
        triggers.append("publish_failure_burst")

    mode = load_operational_mode(rd, settings)
    if triggers and mode not in (OperationalMode.MAINTENANCE,):
        enable_auto_maintenance(rd, reason=";".join(triggers))
        return {"applied": True, "triggers": triggers}
    return {"applied": False, "triggers": triggers, "mode": mode.value}
