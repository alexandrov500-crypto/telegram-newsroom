"""Minimal pipeline: raw → fallback summarize → draft (no desk/governance)."""

from __future__ import annotations

import logging
from datetime import timedelta

from ai.fallback_summarizer import fallback_summarize_cluster
from db.repository import (
    create_draft_and_mark_posts_processed,
    fetch_recent_drafts_for_dedupe,
    merge_draft_extras,
    utcnow,
)
from db.models import RawPost
from db.session import session_scope
from scheduler.runtime_context import PipelineContext
from utils.structured_log import log_event
from utils.text_hash import sha256_hex

logger = logging.getLogger(__name__)


async def try_minimal_draft_from_raw(ctx: PipelineContext, posts: list[RawPost]) -> int | None:
    """Enforced entry: minimal raw → draft via execution wrapper."""
    from app.state.pipeline_execution_wrapper import execute_pipeline_step

    out = await execute_pipeline_step(
        ctx,
        "minimal_draft",
        lambda: _try_minimal_draft_from_raw_impl(ctx, posts),
    )
    return out if isinstance(out, int) else None


async def _try_minimal_draft_from_raw_impl(ctx: PipelineContext, posts: list[RawPost]) -> int | None:
    from app.state.pipeline_execution_wrapper import require_pipeline_wrapper_active

    require_pipeline_wrapper_active("minimal_draft")
    settings = ctx.settings
    if not posts:
        log_event(logger, "summarize_skip_reason", reason="minimal_no_posts", stage="minimal")
        return None

    cluster = posts[:1]
    post = cluster[0]
    log_event(logger, "summarize_entry", mode="minimal", raw_post_id=post.id, channel=post.channel_name)

    sc = fallback_summarize_cluster(cluster, max_body_chars=settings.max_post_chars)
    body = (sc.post_text or "").strip()
    if not body or not sc.used_ids:
        log_event(
            logger,
            "summarize_exit",
            mode="minimal",
            outcome="empty_fallback",
            raw_post_id=post.id,
        )
        return None

    sources_payload = [
        {"channel": post.channel_name, "message_id": int(post.message_id)},
    ]
    content_hash = sha256_hex(body)
    dedupe_since = utcnow() - timedelta(hours=settings.draft_dedupe_window_hours)

    async with session_scope() as session:
        from db.repository import draft_should_be_skipped_as_duplicate

        recent = await fetch_recent_drafts_for_dedupe(session, limit=24, not_older_than=dedupe_since)
        skip, dup_reason = draft_should_be_skipped_as_duplicate(
            new_content=body,
            new_hash=content_hash,
            recent=recent,
            similarity_threshold=settings.draft_similarity_threshold,
        )
        if skip:
            log_event(
                logger,
                "summarize_skip_reason",
                reason=f"minimal_duplicate:{dup_reason}",
                stage="minimal",
            )
            return None

        raw_ids = [int(i) for i in sc.used_ids if i is not None]
        draft = await create_draft_and_mark_posts_processed(
            session,
            content=body,
            content_hash=content_hash,
            sources_payload=sources_payload,
            raw_post_ids=raw_ids,
        )
        draft_id = int(draft.id)
        await merge_draft_extras(
            session,
            draft_id,
            {
                "minimal_pipeline": True,
                "recovery_path": "minimal_raw_to_draft",
                "headline": sc.headline,
            },
        )

    ctx.tick_draft_id = draft_id
    log_event(
        logger,
        "summarize_exit",
        mode="minimal",
        outcome="draft_created",
        draft_id=draft_id,
        raw_post_id=post.id,
    )
    from app.runtime_activity import record_fallback_success
    from app.recovery.pipeline_state_reconciler import note_successful_summarize_tick

    record_fallback_success()
    note_successful_summarize_tick(draft_created=True)
    return draft_id
