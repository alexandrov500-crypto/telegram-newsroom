"""Unified operator panel payload (HTTP + CLI)."""

from __future__ import annotations

import time
from typing import Any

from app.reliability.auto_maintenance import auto_maintenance_snapshot
from app.ops.runtime.execution_lease import read_lease
from app.ops.runtime.node_role import resolve_execution_profile


async def build_operator_summary(settings: Any) -> dict[str, Any]:
    from app.dependency_state import get_dependency_state
    from app.operational_mode import load_operational_mode
    from db.reliability_repository import latest_pipeline_tick, list_due_failed_drafts
    from sqlalchemy import func, select

    from db.models import Draft, DraftStatus, FailedDraftQueue
    from db.session import session_scope

    deps = get_dependency_state()
    profile = resolve_execution_profile(settings)
    lease = read_lease(settings.runtime_state_dir)
    tick = await latest_pipeline_tick()
    failed_due = await list_due_failed_drafts(limit=20)

    pending_drafts = 0
    failed_drafts = 0
    async with session_scope() as session:
        pending_drafts = int(
            await session.scalar(
                select(func.count()).select_from(Draft).where(Draft.status == DraftStatus.PENDING.value)
            )
            or 0
        )
        failed_drafts = int(
            await session.scalar(
                select(func.count()).select_from(Draft).where(Draft.status == DraftStatus.FAILED.value)
            )
            or 0
        )
        retry_pending = int(
            await session.scalar(
                select(func.count())
                .select_from(FailedDraftQueue)
                .where(FailedDraftQueue.status == "pending")
            )
            or 0
        )

    tick_block: dict[str, Any] | None = None
    if tick:
        tick_block = {
            "tick_id": tick.tick_id,
            "status": tick.status,
            "started_at": tick.started_at.isoformat() if tick.started_at else None,
            "finished_at": tick.finished_at.isoformat() if tick.finished_at else None,
            "duration_ms": tick.duration_ms,
            "drafts_created": tick.drafts_created,
            "posts_collected": tick.posts_collected,
            "correlation_id": tick.correlation_id,
        }

    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "execution": {
            "node_role": profile.node_role.value,
            "owner_id": profile.owner_id,
            "lease": lease.to_dict() if lease else None,
        },
        "health": {
            "status": deps.aggregate_status().value,
            "conflict_detected": deps.conflict_detected,
            "openai_circuit": deps.health_payload().get("runtime", {}).get("openai_circuit_state"),
        },
        "operational_mode": load_operational_mode(settings.runtime_state_dir, settings).value,
        "auto_maintenance": auto_maintenance_snapshot(settings.runtime_state_dir),
        "pipeline": {"last_tick": tick_block, "retry_queue_due": len(failed_due)},
        "drafts": {
            "pending": pending_drafts,
            "failed": failed_drafts,
            "retry_pending": retry_pending,
        },
        "alerts_hint": "see var/runtime/ops/pending_notifications.jsonl",
    }
