"""Persistence for pipeline ticks and failed-draft retry queue."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update

from db.models import FailedDraftQueue, PipelineTick
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def insert_pipeline_tick_start(
    *,
    tick_id: str,
    node_name: str,
    correlation_id: str = "",
) -> int:
    row = PipelineTick(
        tick_id=tick_id[:96],
        started_at=_utcnow(),
        status="running",
        node_name=node_name[:128],
        correlation_id=(correlation_id or tick_id)[:96],
    )
    async with session_scope() as session:
        session.add(row)
        await session.flush()
        return int(row.id)


async def complete_pipeline_tick(
    tick_id: str,
    *,
    drafts_created: int = 0,
    posts_collected: int = 0,
    failures: int = 0,
    status: str = "ok",
    detail: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    finished = _utcnow()
    async with session_scope() as session:
        result = await session.execute(select(PipelineTick).where(PipelineTick.tick_id == tick_id[:96]))
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.finished_at = finished
        row.drafts_created = max(0, int(drafts_created))
        row.posts_collected = max(0, int(posts_collected))
        row.failures = max(0, int(failures))
        row.status = status[:32]
        if duration_ms is not None:
            row.duration_ms = max(0, int(duration_ms))
        elif row.started_at:
            started = row.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            row.duration_ms = int((finished - started).total_seconds() * 1000)
        if detail:
            row.detail_json = json.dumps(detail, separators=(",", ":"), default=str)[:8000]


async def mark_pipeline_tick_stale(tick_id: str, *, reason: str = "stuck") -> None:
    """Legacy: prefer finalize_stale_pipeline_ticks for deterministic terminal_state."""
    await finalize_stale_pipeline_tick(
        tick_id,
        terminal_reason=reason[:200] or "stuck_threshold_exceeded",
    )


async def finalize_stale_pipeline_tick(
    tick_id: str,
    *,
    terminal_reason: str = "stale_tick_timeout",
) -> bool:
    """Idempotent: running → reject + committed_reject + finished_at."""
    finished = _utcnow()
    detail = {
        "terminal_state": "committed_reject",
        "terminal_reason": terminal_reason[:240],
        "summarize_idle": f"stale_tick:{terminal_reason[:120]}",
        "publish_outcome": "not_reached",
        "draft_id": None,
        "stale_recovery": True,
    }
    async with session_scope() as session:
        result = await session.execute(
            select(PipelineTick).where(
                PipelineTick.tick_id == tick_id[:96],
                PipelineTick.status == "running",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        started = row.started_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        row.finished_at = finished
        row.status = "reject"
        row.failures = max(int(row.failures or 0), 1)
        if started:
            row.duration_ms = int((finished - started).total_seconds() * 1000)
        row.detail_json = json.dumps(detail, separators=(",", ":"), default=str)[:8000]
        return True


async def finalize_stale_pipeline_ticks(
    *,
    older_than_sec: float,
    terminal_reason: str = "stale_tick_timeout",
) -> list[dict[str, Any]]:
    """Finalize all running ticks older than threshold; returns summary dicts."""
    stuck = await find_stuck_pipeline_ticks(older_than_sec=older_than_sec)
    out: list[dict[str, Any]] = []
    now = _utcnow()
    for row in stuck:
        age_sec = None
        if row.started_at:
            started = row.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age_sec = round((now - started).total_seconds(), 1)
        ok = await finalize_stale_pipeline_tick(
            str(row.tick_id),
            terminal_reason=terminal_reason,
        )
        if ok:
            out.append(
                {
                    "tick_id": str(row.tick_id),
                    "id": int(row.id),
                    "age_sec": age_sec,
                }
            )
    return out


async def find_stuck_pipeline_ticks(*, older_than_sec: float) -> list[PipelineTick]:
    cutoff = _utcnow() - timedelta(seconds=max(30.0, older_than_sec))
    async with session_scope() as session:
        result = await session.execute(
            select(PipelineTick)
            .where(PipelineTick.status == "running", PipelineTick.started_at < cutoff)
            .order_by(PipelineTick.started_at.asc())
            .limit(20)
        )
        return list(result.scalars().all())


async def latest_pipeline_tick() -> PipelineTick | None:
    async with session_scope() as session:
        result = await session.execute(
            select(PipelineTick).order_by(PipelineTick.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()


async def enqueue_failed_draft(
    draft_id: int,
    *,
    error: str,
    error_category: str = "",
    correlation_id: str = "",
    retryable: bool = True,
) -> bool:
    if not retryable:
        return False
    now = _utcnow()
    async with session_scope() as session:
        existing = await session.execute(
            select(FailedDraftQueue).where(FailedDraftQueue.draft_id == int(draft_id))
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            if row.status == "terminal":
                return False
            row.retry_count = int(row.retry_count) + 1
            row.last_error = (error or "")[:4000]
            row.error_category = (error_category or "")[:32]
            row.last_retry_at = now
            row.next_retry_at = _next_retry_at(int(row.retry_count))
            return True
        session.add(
            FailedDraftQueue(
                draft_id=int(draft_id),
                correlation_id=(correlation_id or "")[:96],
                retry_count=0,
                first_failed_at=now,
                last_error=(error or "")[:4000],
                error_category=(error_category or "")[:32],
                status="pending",
                next_retry_at=now,
            )
        )
        log_event(logger, "failed_draft.enqueued", draft_id=draft_id, category=error_category)
        return True


async def mark_failed_draft_terminal(draft_id: int, *, reason: str) -> None:
    async with session_scope() as session:
        result = await session.execute(
            select(FailedDraftQueue).where(FailedDraftQueue.draft_id == int(draft_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.status = "terminal"
        row.terminal_failure_reason = (reason or "")[:2000]


async def get_failed_draft_row(draft_id: int) -> FailedDraftQueue | None:
    async with session_scope() as session:
        result = await session.execute(
            select(FailedDraftQueue).where(FailedDraftQueue.draft_id == int(draft_id))
        )
        return result.scalar_one_or_none()


async def list_due_failed_drafts(*, limit: int = 8) -> list[FailedDraftQueue]:
    now = _utcnow()
    async with session_scope() as session:
        result = await session.execute(
            select(FailedDraftQueue)
            .where(
                FailedDraftQueue.status == "pending",
                FailedDraftQueue.next_retry_at.is_not(None),
                FailedDraftQueue.next_retry_at <= now,
            )
            .order_by(FailedDraftQueue.next_retry_at.asc())
            .limit(max(1, min(limit, 32)))
        )
        return list(result.scalars().all())


async def bump_failed_draft_after_attempt(draft_id: int, *, success: bool, error: str = "") -> None:
    now = _utcnow()
    async with session_scope() as session:
        result = await session.execute(
            select(FailedDraftQueue).where(FailedDraftQueue.draft_id == int(draft_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        if success:
            await session.delete(row)
            return
        row.retry_count = int(row.retry_count) + 1
        row.last_retry_at = now
        row.last_error = (error or row.last_error or "")[:4000]
        row.next_retry_at = _next_retry_at(int(row.retry_count))


def _next_retry_at(retry_count: int) -> datetime:
    """Exponential backoff: 2^n minutes capped at 6h."""
    minutes = min(360, max(2, 2 ** min(retry_count, 8)))
    return _utcnow() + timedelta(minutes=minutes)
