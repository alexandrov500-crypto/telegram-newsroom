"""Digest scheduler jobs — morning, evening, weekly."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram.enums import ParseMode

from app.digest.intelligence import run_digest_generation
from db.models import GrowthDigestRun
from db.session import session_scope
from sqlalchemy import select
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_digest_tick(ctx: object) -> dict[str, object]:
    settings = ctx.settings  # type: ignore[attr-defined]
    bot = ctx.bot  # type: ignore[attr-defined]
    result: dict[str, object] = {"published": False}

    if os.getenv("GROWTH_DIGEST_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        result["reason"] = "disabled"
        return result

    tz_name = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now_local = datetime.now(UTC)
    hour = now_local.hour
    weekday = now_local.weekday()

    digest_type = ""
    since_hours = 12
    if 7 <= hour < 9:
        digest_type = "morning_briefing"
        since_hours = 14
    elif 19 <= hour < 21:
        digest_type = "evening_recap"
        since_hours = 12
    elif weekday == 6 and 10 <= hour < 12:
        digest_type = "weekly_key_events"
        since_hours = 168
    else:
        result["reason"] = "outside_digest_window"
        return result

    gen = await run_digest_generation(digest_type=digest_type, since_hours=since_hours)
    if gen.get("skipped"):
        result.update(gen)
        return result

    digest_id = int(gen.get("digest_id") or 0)
    async with session_scope() as session:
        row = (await session.execute(select(GrowthDigestRun).where(GrowthDigestRun.id == digest_id))).scalar_one_or_none()
        if row is None or not row.content:
            result["reason"] = "missing_content"
            return result
        html = row.content

    if getattr(settings, "dry_run", False):
        result["reason"] = "dry_run"
        return result

    try:
        msg = await bot.send_message(
            chat_id=int(settings.channel_id),
            text=html,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        msg_id = int(msg.message_id)
    except Exception as exc:
        log_event(logger, "digest.publish_failed", digest_id=digest_id, error=repr(exc)[:200])
        result["reason"] = f"publish_failed:{repr(exc)[:80]}"
        return result

    async with session_scope() as session:
        row = (await session.execute(select(GrowthDigestRun).where(GrowthDigestRun.id == digest_id))).scalar_one_or_none()
        if row:
            row.status = "published"
            row.telegram_message_id = msg_id
            row.published_at = datetime.now(UTC)

    result["published"] = True
    result["digest_id"] = digest_id
    result["message_id"] = msg_id
    log_event(logger, "digest.tick_complete", digest_type=digest_type, message_id=msg_id)
    return result
