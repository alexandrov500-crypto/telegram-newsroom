"""Wire backlog — fresh-first fetch and stale skip for top-channel cadence."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RawPost
from db.repository import utcnow


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def wire_backlog_enabled() -> bool:
    raw = os.getenv("WIRE_BACKLOG_FRESH_FIRST", "").strip().lower()
    if raw in {"off", "false", "0", "no"}:
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        return news_channel_beat_enabled()
    except Exception:
        return False


def wire_stale_skip_hours() -> float:
    return float(_env_int("WIRE_STALE_SKIP_HOURS", 24, lo=6, hi=168))


def wire_fresh_window_hours() -> float:
    return float(_env_int("WIRE_FRESH_WINDOW_HOURS", 8, lo=2, hi=48))


async def skip_stale_wire_backlog(session: AsyncSession, *, batch_limit: int = 500) -> int:
    """Mark ancient unprocessed raw posts as processed so pipeline focuses on live wire."""
    if not wire_backlog_enabled():
        return 0
    cutoff = datetime.now(UTC) - timedelta(hours=wire_stale_skip_hours())
    when = utcnow()
    ids = list(
        (
            await session.execute(
                select(RawPost.id)
                .where(RawPost.processed_at.is_(None), RawPost.created_at < cutoff)
                .order_by(RawPost.created_at.asc())
                .limit(batch_limit)
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return 0
    await session.execute(update(RawPost).where(RawPost.id.in_(ids)).values(processed_at=when))
    return len(ids)


def _fastlane_keys() -> set[str]:
    try:
        from app.ops.autonomous_publish import _auto_publish_fastlane_sources

        out: set[str] = set()
        for h in _auto_publish_fastlane_sources():
            key = str(h).strip().lower()
            if not key:
                continue
            out.add(key)
            out.add(key.lstrip("@"))
        return out
    except Exception:
        return set()


async def fetch_wire_unprocessed_posts(session: AsyncSession, limit: int) -> list[RawPost]:
    """
    Fresh-first: prefer recent posts from fastlane sources (newest first).
    Falls back to any recent unprocessed, then oldest fresh remainder.
    """
    if not wire_backlog_enabled():
        from db.repository import fetch_unprocessed_raw_posts

        return await fetch_unprocessed_raw_posts(session, limit=limit)

    fresh_cutoff = datetime.now(UTC) - timedelta(hours=wire_fresh_window_hours())
    stale_cutoff = datetime.now(UTC) - timedelta(hours=wire_stale_skip_hours())
    fastlane = _fastlane_keys()
    picked: list[RawPost] = []
    seen: set[int] = set()

    async def _take(stmt) -> None:
        nonlocal picked
        if len(picked) >= limit:
            return
        rows = list((await session.execute(stmt)).scalars().all())
        for row in rows:
            rid = int(row.id)
            if rid in seen:
                continue
            seen.add(rid)
            picked.append(row)
            if len(picked) >= limit:
                break

    base = (
        select(RawPost)
        .where(
            RawPost.processed_at.is_(None),
            RawPost.created_at >= stale_cutoff,
        )
        .order_by(RawPost.created_at.desc())
    )

    if fastlane:
        fl_rows = list(
            (
                await session.execute(
                    base.where(RawPost.created_at >= fresh_cutoff).limit(max(limit * 4, 40))
                )
            )
            .scalars()
            .all()
        )
        for row in sorted(
            fl_rows,
            key=lambda r: (
                0
                if str(getattr(r, "channel_name", "") or "").lower().lstrip("@")
                in {k.lstrip("@") for k in fastlane}
                else 1,
                -(getattr(r, "created_at", datetime.min.replace(tzinfo=UTC)).timestamp()),
            ),
        ):
            rid = int(row.id)
            if rid in seen:
                continue
            seen.add(rid)
            picked.append(row)
            if len(picked) >= limit:
                return picked

    await _take(base.limit(limit))
    return picked[:limit]
