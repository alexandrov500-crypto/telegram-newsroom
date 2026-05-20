"""Persist runtime ops transitions (SQLite/PostgreSQL)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.dependency_state import get_dependency_state
from db.models import RuntimeOpsState
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state_blob() -> dict[str, Any]:
    deps = get_dependency_state()
    return {
        "telegram_mode": deps.telegram_mode,
        "conflict_detected": deps.conflict_detected,
        "polling_active": deps.polling_active,
        "polling_retry_count": deps.polling_retry_count,
        "polling_conflict_count": deps.polling_conflict_count,
        "aggregate": deps.aggregate_status().value,
        "recorded_unix": time.time(),
    }


async def persist_runtime_ops_state() -> None:
    deps = get_dependency_state()
    blob = _state_blob()
    async with session_scope() as session:
        row = await session.get(RuntimeOpsState, 1)
        if row is None:
            row = RuntimeOpsState(id=1)
            session.add(row)
        row.polling_instance_id = deps.polling_instance_id or ""
        row.last_degraded_reason = deps.last_degraded_reason or ""
        row.consecutive_failures = int(deps.consecutive_failures)
        row.last_transition_at = _utcnow()
        if deps.last_recovery_at_iso:
            try:
                row.last_recovery_at = datetime.fromisoformat(
                    deps.last_recovery_at_iso.replace("Z", "+00:00")
                )
            except ValueError:
                row.last_recovery_at = _utcnow()
        row.state_json = json.dumps(blob, separators=(",", ":"))


async def load_runtime_ops_state() -> dict[str, Any] | None:
    async with session_scope() as session:
        result = await session.execute(select(RuntimeOpsState).where(RuntimeOpsState.id == 1))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        out = {
            "polling_instance_id": row.polling_instance_id,
            "last_degraded_reason": row.last_degraded_reason,
            "last_recovery_at": row.last_recovery_at.isoformat() if row.last_recovery_at else None,
            "consecutive_failures": row.consecutive_failures,
            "last_transition_at": row.last_transition_at.isoformat() if row.last_transition_at else None,
        }
        try:
            out["state_json"] = json.loads(row.state_json or "{}")
        except json.JSONDecodeError:
            out["state_json"] = {}
        return out


def apply_loaded_runtime_ops(data: dict[str, Any] | None) -> None:
    if not data:
        return
    deps = get_dependency_state()
    if data.get("polling_instance_id"):
        deps.polling_instance_id = str(data["polling_instance_id"])
    deps.last_degraded_reason = str(data.get("last_degraded_reason") or "")
    deps.consecutive_failures = int(data.get("consecutive_failures") or 0)
    if data.get("last_recovery_at"):
        deps.last_recovery_at_iso = str(data["last_recovery_at"])


def persist_runtime_ops_state_fire_and_forget() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist_safe(), name="runtime_ops_persist")
    except RuntimeError:
        pass


async def _persist_safe() -> None:
    try:
        await persist_runtime_ops_state()
    except Exception as exc:
        log_event(logger, "runtime_ops.persist_failed", error=repr(exc)[:300])
