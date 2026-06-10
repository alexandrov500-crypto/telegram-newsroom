"""Scheduler jobs for Telegram analytics polling."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select

from app.analytics.telegram_stats import poll_pending_post_metrics, purge_old_analytics, snapshot_channel_audience
from collector.telethon_client import build_telethon_client
from collector.telethon_connect import connect_telethon_resilient
from db.models import PostPerformance
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_analytics_tick(ctx: object) -> dict[str, int | str]:
    settings = ctx.settings  # type: ignore[attr-defined]
    result: dict[str, int | str] = {"snapshots": 0, "audience": 0, "purged": 0}
    try:
        count = await snapshot_channel_audience(ctx.bot, channel_id=int(settings.channel_id))  # type: ignore[attr-defined]
        if count is not None:
            result["audience"] = count
    except Exception as exc:
        log_event(logger, "analytics.audience_tick_failed", error=repr(exc)[:120])

    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )
    if await connect_telethon_resilient(client, label="analytics_poll"):
        try:
            result["snapshots"] = await poll_pending_post_metrics(client, channel_id=int(settings.channel_id))
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    try:
        async with session_scope() as session:
            avg = (
                await session.execute(
                    select(func.avg(PostPerformance.engagement_score)).where(
                        PostPerformance.snapshot_label.in_(("t1h", "t6h"))
                    )
                )
            ).scalar()
            avg_f = float(avg or 0.0)
        cache = Path(settings.runtime_state_dir) / "analytics_engagement_avg.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"avg_engagement_score": round(avg_f, 4)}), encoding="utf-8")
    except Exception:
        pass

    try:
        result["purged"] = await purge_old_analytics()
    except Exception:
        pass

    try:
        from app.growth.feedback_job import run_growth_feedback_tick

        growth_result = await run_growth_feedback_tick(ctx)
        result["growth_feedback"] = growth_result
    except Exception as exc:
        log_event(logger, "growth.feedback_tick_failed", error=repr(exc)[:120])

    try:
        from app.growth_layer.validation.scheduler_jobs import run_growth_validation_tick

        validation_result = await run_growth_validation_tick(ctx)
        result["growth_validation"] = validation_result
    except Exception as exc:
        log_event(logger, "growth.validation_tick_failed", error=repr(exc)[:120])

    log_event(logger, "analytics.tick_complete", **{k: v for k, v in result.items()})
    return result
