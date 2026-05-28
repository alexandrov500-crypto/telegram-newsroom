"""Persist operator feedback rows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.models import OperatorFeedback
from db.session import session_scope


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def insert_operator_feedback(
    *,
    operator_id: int,
    action: str,
    tick_id: str = "",
    draft_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    async with session_scope() as session:
        row = OperatorFeedback(
            created_at=_utcnow(),
            operator_id=int(operator_id),
            tick_id=(tick_id or "")[:96],
            draft_id=draft_id,
            action=str(action)[:48],
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str)[:8000],
            applied=0,
            apply_reason="",
        )
        session.add(row)
        await session.flush()
        return int(row.id)


async def mark_feedback_applied(feedback_id: int, *, reason: str = "applied") -> None:
    async with session_scope() as session:
        result = await session.execute(
            select(OperatorFeedback).where(OperatorFeedback.id == int(feedback_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.applied = 1
        row.apply_reason = (reason or "applied")[:240]


async def list_recent_feedback(*, limit: int = 50) -> list[dict[str, Any]]:
    async with session_scope() as session:
        result = await session.execute(
            select(OperatorFeedback).order_by(OperatorFeedback.id.desc()).limit(max(1, limit))
        )
        rows = result.scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            meta = json.loads(r.metadata_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "operator_id": r.operator_id,
                "tick_id": r.tick_id,
                "draft_id": r.draft_id,
                "action": r.action,
                "metadata": meta,
                "applied": bool(r.applied),
                "apply_reason": r.apply_reason,
            }
        )
    return out
