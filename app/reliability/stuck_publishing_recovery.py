"""Recover drafts stuck in PUBLISHING (crash / hung Telegram upload)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import select

from db.models import Draft, DraftStatus, PublishedPost
from db.repository import (
    get_draft_by_id,
    mark_draft_published,
    rollback_draft_publishing_to_pending,
    utcnow,
)
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _stuck_ttl_sec() -> float:
    raw = os.getenv("PUBLISHING_STUCK_TTL_SEC", "180").strip()
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 180.0


def _draft_age_sec(draft: Draft) -> float:
    anchor = draft.moderated_at or draft.created_at
    if anchor is None:
        return 0.0
    return max(0.0, (utcnow() - anchor).total_seconds())


async def _published_message_id(session, draft_id: int) -> int | None:
    row = await session.scalar(
        select(PublishedPost.telegram_post_id).where(PublishedPost.draft_id == draft_id).limit(1)
    )
    if row is None:
        return None
    try:
        return int(row)
    except (TypeError, ValueError):
        return None


async def rollback_stale_publishing_draft(
    session,
    draft_id: int,
    *,
    force: bool = False,
    ttl_sec: float | None = None,
) -> str:
    """
    Reconcile or rollback a PUBLISHING draft.
    Returns: reconciled | rolled_back | fresh | not_publishing | missing
    """
    draft = await get_draft_by_id(session, draft_id)
    if draft is None:
        return "missing"
    if draft.status != DraftStatus.PUBLISHING.value:
        return "not_publishing"

    mid = await _published_message_id(session, draft_id)
    if mid is not None:
        await mark_draft_published(session, draft_id, mid)
        log_event(logger, "publish.stuck_reconciled", draft_id=draft_id, channel_message_id=mid)
        return "reconciled"

    ttl = ttl_sec if ttl_sec is not None else _stuck_ttl_sec()
    age = _draft_age_sec(draft)
    if not force and age < ttl:
        return "fresh"

    ok = await rollback_draft_publishing_to_pending(session, draft_id)
    if ok:
        log_event(logger, "publish.stuck_rolled_back", draft_id=draft_id, age_sec=round(age, 1), force=force)
        return "rolled_back"
    return "not_publishing"


async def recover_stuck_publishing_batch(
    settings: Any,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Heartbeat: rollback stale PUBLISHING drafts so operator retry / auto-retry can proceed."""
    ttl = _stuck_ttl_sec()
    outcomes: list[dict[str, Any]] = []
    async with session_scope() as session:
        rows = await session.scalars(
            select(Draft)
            .where(Draft.status == DraftStatus.PUBLISHING.value)
            .order_by(Draft.id.desc())
            .limit(max(1, min(int(limit), 32)))
        )
        for draft in rows:
            age = _draft_age_sec(draft)
            if age < ttl:
                continue
            result = await rollback_stale_publishing_draft(
                session,
                int(draft.id),
                force=False,
                ttl_sec=ttl,
            )
            if result in {"reconciled", "rolled_back"}:
                outcomes.append({"draft_id": int(draft.id), "result": result, "age_sec": round(age, 1)})
    if outcomes:
        log_event(logger, "publish.stuck_recovery_batch", count=len(outcomes), outcomes=outcomes[:8])
    return {"recovered": len(outcomes), "outcomes": outcomes}
