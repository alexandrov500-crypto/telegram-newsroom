"""Telegram post metrics polling and audience snapshots."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engagement_scoring import engagement_score, metrics_to_trend_memory_payload, virality_score
from db.models import ChannelAudienceSnapshot, PostPerformance
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_SNAPSHOT_SCHEDULE = ("t0", "t1h", "t6h", "t24h")
_SNAPSHOT_DELAYS_H = {"t0": 0.05, "t1h": 1.0, "t6h": 6.0, "t24h": 24.0}


def _analytics_enabled() -> bool:
    return os.getenv("TELEGRAM_ANALYTICS_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _retention_days() -> int:
    try:
        return max(7, min(365, int(os.getenv("TELEGRAM_ANALYTICS_RETENTION_DAYS", "90"))))
    except ValueError:
        return 90


async def enqueue_post_for_tracking(
    *,
    draft_id: int | None,
    telegram_post_id: int,
    channel_id: int,
    published_at: datetime | None = None,
    primary_source: str = "",
    topic_bucket: str = "general",
    publish_hour_local: int = 0,
) -> None:
    """Record t0 placeholder; poll job fills metrics on schedule."""
    if not _analytics_enabled():
        return
    now = published_at or datetime.now(UTC)
    async with session_scope() as session:
        row = PostPerformance(
            draft_id=int(draft_id) if draft_id is not None else None,
            telegram_post_id=int(telegram_post_id),
            channel_id=int(channel_id),
            published_at=now,
            snapshot_label="t0",
            snapshot_at=now,
            views=0,
            forwards=0,
            reactions_total=0,
            subscribers_at_snapshot=0,
            engagement_score=0.0,
            virality_score=0.0,
            primary_source=(primary_source or "")[:255],
            topic_bucket=(topic_bucket or "general")[:64],
            publish_hour_local=int(publish_hour_local) % 24,
            extras_json=json.dumps({"pending_snapshots": list(_SNAPSHOT_SCHEDULE[1:])}),
        )
        session.add(row)
        log_event(
            logger,
            "analytics.post_enqueued",
            draft_id=draft_id,
            telegram_post_id=telegram_post_id,
        )


async def _latest_subscribers(session: AsyncSession, channel_id: int) -> int:
    q = (
        select(ChannelAudienceSnapshot)
        .where(ChannelAudienceSnapshot.channel_id == int(channel_id))
        .order_by(ChannelAudienceSnapshot.captured_at.desc())
        .limit(1)
    )
    row = (await session.execute(q)).scalar_one_or_none()
    return int(row.member_count) if row else 0


def _extract_message_stats(msg: Any) -> tuple[int, int, int]:
    views = int(getattr(msg, "views", None) or 0)
    forwards = int(getattr(msg, "forwards", None) or 0)
    reactions = 0
    rx = getattr(msg, "reactions", None)
    if rx is not None:
        results = getattr(rx, "results", None) or []
        reactions = sum(int(getattr(r, "count", 0) or 0) for r in results)
    return views, forwards, reactions


async def poll_pending_post_metrics(client: Any, *, channel_id: int) -> int:
    """
    Poll Telethon message stats for posts due for snapshot.
    Returns number of snapshots written.
    """
    if not _analytics_enabled() or client is None:
        return 0
    now = datetime.now(UTC)
    updated = 0
    async with session_scope() as session:
        q = (
            select(PostPerformance)
            .where(PostPerformance.snapshot_label == "t0")
            .order_by(PostPerformance.published_at.desc())
            .limit(int(os.getenv("TELEGRAM_ANALYTICS_POLL_BATCH", "40")))
        )
        rows = list((await session.execute(q)).scalars().all())
        subs = await _latest_subscribers(session, channel_id)
        for base in rows:
            try:
                extras = json.loads(base.extras_json or "{}")
            except (json.JSONDecodeError, TypeError):
                extras = {}
            pending = list(extras.get("pending_snapshots") or [])
            if not pending:
                continue
            age_h = (now - base.published_at).total_seconds() / 3600.0
            due: list[str] = []
            keep: list[str] = []
            for label in pending:
                if age_h >= float(_SNAPSHOT_DELAYS_H.get(label, 999)):
                    due.append(label)
                else:
                    keep.append(label)
            if not due:
                continue
            try:
                msgs = await client.get_messages(channel_id, ids=[base.telegram_post_id])
                msg = msgs[0] if msgs else None
            except Exception as exc:
                log_event(logger, "analytics.poll_failed", draft_id=base.draft_id, error=repr(exc)[:120])
                continue
            if msg is None:
                extras["pending_snapshots"] = keep
                base.extras_json = json.dumps(extras)
                continue
            views, forwards, reactions = _extract_message_stats(msg)
            label = due[-1]
            hrs = max(age_h, 0.1)
            eng = engagement_score(
                views=views,
                forwards=forwards,
                reactions=reactions,
                subscribers=subs,
                hours_since_publish=hrs,
            )
            vir = virality_score(views=views, forwards=forwards, subscribers=subs)
            snap = PostPerformance(
                draft_id=base.draft_id,
                telegram_post_id=base.telegram_post_id,
                channel_id=base.channel_id,
                published_at=base.published_at,
                snapshot_label=label,
                snapshot_at=now,
                views=views,
                forwards=forwards,
                reactions_total=reactions,
                subscribers_at_snapshot=subs,
                engagement_score=eng,
                virality_score=vir,
                primary_source=base.primary_source,
                topic_bucket=base.topic_bucket,
                publish_hour_local=base.publish_hour_local,
                extras_json="{}",
            )
            session.add(snap)
            base.views = views
            base.forwards = forwards
            base.reactions_total = reactions
            base.engagement_score = eng
            base.virality_score = vir
            extras["pending_snapshots"] = keep
            base.extras_json = json.dumps(extras)
            updated += 1
            try:
                from app.analytics.trend_bridge import feed_real_metrics_to_trend_memory

                await feed_real_metrics_to_trend_memory(
                    draft_id=base.draft_id,
                    topic_bucket=base.topic_bucket,
                    metrics={
                        "views": views,
                        "forwards": forwards,
                        "reactions_total": reactions,
                        "subscribers_at_snapshot": subs,
                        "hours_since_publish": hrs,
                    },
                )
            except Exception:
                pass
    if updated:
        log_event(logger, "analytics.poll_complete", snapshots=updated)
    return updated


async def snapshot_channel_audience(bot: Any, *, channel_id: int) -> int | None:
    """Bot API getChatMemberCount → channel_audience_snapshots."""
    if not _analytics_enabled() or bot is None:
        return None
    try:
        count = int(await bot.get_chat_member_count(channel_id))
    except Exception as exc:
        log_event(logger, "analytics.audience_failed", error=repr(exc)[:120])
        return None
    now = datetime.now(UTC)
    async with session_scope() as session:
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)
        q24 = (
            select(ChannelAudienceSnapshot)
            .where(
                ChannelAudienceSnapshot.channel_id == int(channel_id),
                ChannelAudienceSnapshot.captured_at <= day_ago,
            )
            .order_by(ChannelAudienceSnapshot.captured_at.desc())
            .limit(1)
        )
        q7 = (
            select(ChannelAudienceSnapshot)
            .where(
                ChannelAudienceSnapshot.channel_id == int(channel_id),
                ChannelAudienceSnapshot.captured_at <= week_ago,
            )
            .order_by(ChannelAudienceSnapshot.captured_at.desc())
            .limit(1)
        )
        r24 = (await session.execute(q24)).scalar_one_or_none()
        r7 = (await session.execute(q7)).scalar_one_or_none()
        delta_24h = count - int(r24.member_count) if r24 else 0
        delta_7d = count - int(r7.member_count) if r7 else 0
        session.add(
            ChannelAudienceSnapshot(
                channel_id=int(channel_id),
                captured_at=now,
                member_count=count,
                delta_24h=delta_24h,
                delta_7d=delta_7d,
            )
        )
    log_event(logger, "analytics.audience_snapshot", member_count=count, delta_24h=delta_24h)
    return count


async def purge_old_analytics() -> int:
    """Retention policy for analytics tables."""
    cutoff = datetime.now(UTC) - timedelta(days=_retention_days())
    deleted = 0
    async with session_scope() as session:
        from sqlalchemy import delete

        r1 = await session.execute(delete(PostPerformance).where(PostPerformance.snapshot_at < cutoff))
        r2 = await session.execute(delete(ChannelAudienceSnapshot).where(ChannelAudienceSnapshot.captured_at < cutoff))
        deleted = int(r1.rowcount or 0) + int(r2.rowcount or 0)
    return deleted
