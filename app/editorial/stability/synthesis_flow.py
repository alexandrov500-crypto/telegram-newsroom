"""Async orchestration — synthesis / elastic fill draft creation."""

from __future__ import annotations

import logging
from typing import Any

from app.editorial.stability.config import stability_layer_enabled
from app.editorial.stability.controller import (
    content_hash_for_text,
    enrich_draft_for_stability,
    evaluate_stability_context,
    sources_payload_for_synthesis,
)
from app.editorial.stability.elastic_fill import build_context_post_from_buffer, pick_elastic_cluster
from app.editorial.stability.growth_decision import evaluate_growth_decision
from app.editorial.stability.synthesis import build_synthesis_post, mark_synthesis_emitted
from db.repository import create_draft_and_mark_posts_processed, merge_draft_extras
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def try_create_stability_draft(
    ctx: Any,
    *,
    trigger: str,
    exclude_fingerprint: str = "",
) -> bool:
    """
    MODE B/C fill — create draft without raw posts when anti-pause demands continuity.
    Returns True if draft was created and ctx.tick_draft_id set.
    """
    if not stability_layer_enabled():
        return False

    settings = ctx.settings
    rd = settings.runtime_state_dir
    stab = evaluate_stability_context(
        newsroom_tz=getattr(settings, "newsroom_timezone", "Europe/Moscow"),
        no_raw_posts=True,
        governance_blocked=trigger == "governance",
        desk_blocked=trigger == "desk",
    )
    if not stab.anti_pause.anti_pause_active and not stab.allow_synthesis:
        return False

    body: str | None = None
    mode = "editorial_synthesis"
    meta: dict[str, Any] = {"trigger": trigger}

    if stab.mode.value == "elastic_fill" or trigger == "governance":
        picked = pick_elastic_cluster(rd, exclude_fingerprint=exclude_fingerprint)
        if picked:
            body = build_context_post_from_buffer(picked)
            mode = "elastic_fill"
            meta.update({"fingerprint": picked.fingerprint, "elastic": True})

    if not body:
        synth = build_synthesis_post(rd, newsroom_tz=getattr(settings, "newsroom_timezone", "Europe/Moscow"))
        if synth:
            body, synth_meta = synth
            meta.update(synth_meta)
            mark_synthesis_emitted(rd)

    if not body:
        return False

    decision = evaluate_growth_decision(body, quality_score=52.0, publishing_mode=mode)
    if decision.reject:
        return False

    packaged, extras = enrich_draft_for_stability(
        body,
        runtime_dir=rd,
        editorial_category="context",
        quality_score=52.0,
        is_breaking=False,
        publishing_mode=mode,
        sources=[],
    )
    if extras.get("stability_reject"):
        return False

    content_hash = content_hash_for_text(packaged)
    sources_payload = sources_payload_for_synthesis(meta)

    try:
        async with session_scope() as session:
            draft = await create_draft_and_mark_posts_processed(
                session,
                content=packaged,
                content_hash=content_hash,
                sources_payload=sources_payload,
                raw_post_ids=[],
            )
            draft_id = int(draft.id)
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "editorial_stability": extras.get("editorial_stability"),
                    "stability_fill": meta,
                },
            )
    except Exception as exc:
        log_event(logger, "stability.draft_create_failed", error=repr(exc)[:200], trigger=trigger)
        return False

    ctx.tick_draft_id = draft_id
    ctx.tick_summarize_idle_reason = ""
    log_event(
        logger,
        "stability.draft_created",
        draft_id=draft_id,
        mode=mode,
        trigger=trigger,
        anti_pause=stab.anti_pause.reason,
    )
    return True
