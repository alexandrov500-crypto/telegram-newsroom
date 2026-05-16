"""Default job handlers (stubs + publisher wiring to publish_service)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from worker.job_queue import JobEnvelope

from workers.dispatcher import HandlerContext, HandlerRegistry
from workers.types import ErrorClass, JobType, StructuredJobError
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def _noop(ctx: HandlerContext, job: JobEnvelope, *, label: str) -> None:
    log_event(
        logger,
        "worker.handler.noop",
        label=label,
        job_type=(job.payload or {}).get("job_type"),
        delivery_id=(job.payload or {}).get("delivery_id"),
        worker_role=ctx.worker_role,
    )


async def _publish_draft(ctx: HandlerContext, job: JobEnvelope) -> None:
    from publisher.publish_service import execute_admin_publication_flow

    raw = job.payload.get("draft_id")
    if raw is None:
        raise StructuredJobError("draft_id required", classification=ErrorClass.PERMANENT)
    draft_id = int(raw)
    idem = job.payload.get("idempotency_key")
    idem_s = str(idem) if idem is not None else None
    bot = ctx.bot
    if bot is None:
        bot = Bot(ctx.settings.bot_token, parse_mode=ParseMode.HTML)
    res = await execute_admin_publication_flow(bot, ctx.settings, draft_id, idempotency_key=idem_s)
    log_event(
        logger,
        "worker.handler.publish_done",
        outcome=res.outcome.value,
        draft_id=draft_id,
        worker_role=ctx.worker_role,
    )


def build_ingest_registry() -> HandlerRegistry:
    r = HandlerRegistry()
    r.register_fn(JobType.INGEST_ARTICLE, lambda ctx, job: _noop(ctx, job, label="ingest_article"))
    return r


def build_ai_registry() -> HandlerRegistry:
    r = HandlerRegistry()

    async def _cluster(ctx: HandlerContext, job: JobEnvelope) -> None:
        await _noop(ctx, job, label="process_cluster")

    async def _summary(ctx: HandlerContext, job: JobEnvelope) -> None:
        await _noop(ctx, job, label="generate_summary")

    async def _preview(ctx: HandlerContext, job: JobEnvelope) -> None:
        await _noop(ctx, job, label="generate_preview")

    r.register_fn(JobType.PROCESS_CLUSTER, _cluster)
    r.register_fn(JobType.GENERATE_SUMMARY, _summary)
    r.register_fn(JobType.GENERATE_PREVIEW, _preview)
    return r


def build_publisher_registry() -> HandlerRegistry:
    r = HandlerRegistry()
    r.register_fn(JobType.PUBLISH_DRAFT, _publish_draft)
    return r
