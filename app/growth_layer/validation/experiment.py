"""Experiment tracking: CB Brief vs Growth Brief per published post."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def validation_enabled() -> bool:
    raw = os.getenv("GROWTH_VALIDATION_ENABLED", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _experiment_payload(
    *,
    format_profile: str,
    predicted_virality: int,
    virality_tier: str = "",
    topic_bucket: str = "general",
    primary_source: str = "",
) -> dict[str, Any]:
    return {
        "format_profile": format_profile,
        "predicted_virality": int(predicted_virality),
        "virality_tier": virality_tier,
        "topic_bucket": topic_bucket,
        "primary_source": primary_source,
    }


async def record_publish_experiment(
    session: AsyncSession,
    *,
    draft_id: int,
    telegram_post_id: int,
    published_at: datetime | None,
    extras_json: str | None,
    topic_bucket: str = "general",
    primary_source: str = "",
) -> None:
    """Persist experiment row at publish time (predicted side only)."""
    if not validation_enabled():
        return
    from app.growth_layer.format.profiles import effective_format_profile, growth_meta_from_draft_extras
    from app.growth_layer.segments.content_segments import classify_content_segment
    from db.growth_validation_repository import upsert_post_growth_validation_publish

    growth = growth_meta_from_draft_extras(extras_json)
    format_profile = effective_format_profile(growth)
    predicted = 0
    tier = ""
    if growth:
        try:
            predicted = int(growth.get("virality_score") or 0)
        except (TypeError, ValueError):
            predicted = 0
        tier = str(growth.get("virality_tier") or "")

    if predicted <= 0:
        from db.growth_scores_repository import get_draft_growth_score

        row = await get_draft_growth_score(session, int(draft_id))
        if row is not None:
            predicted = int(row.virality_score)
            tier = str(row.virality_tier or tier)
            if not format_profile or format_profile == "cb_brief":
                format_profile = str(row.format_profile or format_profile)

    experiment = _experiment_payload(
        format_profile=format_profile,
        predicted_virality=predicted,
        virality_tier=tier,
        topic_bucket=topic_bucket,
        primary_source=primary_source,
    )
    content_segment = classify_content_segment(
        {"draft_extras": extras_json, "topic_bucket": topic_bucket, "category": topic_bucket}
    )

    await upsert_post_growth_validation_publish(
        session,
        draft_id=int(draft_id),
        telegram_post_id=int(telegram_post_id),
        published_at=published_at or _utcnow(),
        format_profile=format_profile,
        predicted_virality=predicted,
        virality_tier=tier,
        topic_bucket=topic_bucket,
        primary_source=primary_source,
        experiment_json=json.dumps(experiment, ensure_ascii=False),
        content_segment=content_segment,
    )
    log_event(
        logger,
        "growth.validation.publish_recorded",
        draft_id=draft_id,
        format_profile=format_profile,
        predicted_virality=predicted,
    )


async def finalize_post_validation(
    session: AsyncSession,
    *,
    draft_id: int | None,
    telegram_post_id: int,
    snapshot_label: str,
    views: int,
    forwards: int,
    reactions: int,
    subscribers: int,
    engagement_score: float,
    virality_score: float,
    hours_since_publish: float,
) -> None:
    """Attach t24h (or latest) actuals to experiment row."""
    if not validation_enabled() or draft_id is None:
        return
    if snapshot_label not in {"t6h", "t24h"}:
        return
    from app.growth_layer.validation.acquisition_proxy import compute_acquisition_components
    from app.growth_layer.validation.status import ValidationStatus, status_for_snapshot
    from db.growth_validation_repository import update_post_growth_validation_actuals

    subs = max(subscribers, 1)
    err = round(views / subs, 4)
    forward_rate = round(forwards / max(views, 1), 4)
    engagement = round(float(engagement_score), 4)
    components = compute_acquisition_components(
        forwards=float(forwards),
        err=err,
        engagement=engagement,
    )
    actuals = {
        "actual_engagement": engagement,
        "actual_forwards": int(forwards),
        "actual_views": int(views),
        "actual_reactions": int(reactions),
        "actual_err": err,
        "actual_forward_rate": forward_rate,
        "actual_virality_score": round(float(virality_score), 4),
        "snapshot_label": snapshot_label,
        "hours_since_publish": round(float(hours_since_publish), 2),
        **components,
    }
    vstatus = status_for_snapshot(snapshot_label)
    validation_status = vstatus.value if vstatus else ValidationStatus.PENDING.value
    await update_post_growth_validation_actuals(
        session,
        draft_id=int(draft_id),
        actuals_json=json.dumps(actuals, ensure_ascii=False),
        validated_at=_utcnow(),
        prefer_label="t24h" if snapshot_label == "t24h" else "t6h",
        validation_status=validation_status,
    )
    log_event(
        logger,
        "growth.validation.actuals_recorded",
        draft_id=draft_id,
        snapshot_label=snapshot_label,
        err=err,
        forwards=forwards,
    )
    if snapshot_label == "t24h":
        try:
            from db.growth_validation_repository import get_post_growth_validation_by_draft
            from db.repository import get_draft_by_id

            val_row = await get_post_growth_validation_by_draft(session, int(draft_id))
            draft = await get_draft_by_id(session, int(draft_id))
            if val_row is not None and draft is not None:
                from app.growth_layer.advisor_validation.record import record_advisor_outcomes_for_draft

                await record_advisor_outcomes_for_draft(
                    session,
                    draft_id=int(draft_id),
                    telegram_post_id=int(val_row.telegram_post_id),
                    content=draft.content or "",
                    sources=draft.sources or "[]",
                    draft_extras=draft.draft_extras,
                    editor_title=draft.editor_title,
                    editor_summary=draft.editor_summary,
                    actuals=actuals,
                )
        except Exception:
            pass
