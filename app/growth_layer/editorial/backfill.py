"""Backfill post_editorial_features from historical drafts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.editorial.feature_extraction import draft_to_post_dict, extract_editorial_features
from app.growth_layer.segments.content_segments import classify_from_draft_extras
from db.editorial_features_repository import upsert_post_editorial_features
from db.models import Draft, PostGrowthValidation
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass
class EditorialBackfillStats:
    scanned: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


async def backfill_editorial_features(
    session: AsyncSession,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> EditorialBackfillStats:
    stats = EditorialBackfillStats(dry_run=dry_run)
    validations = list((await session.execute(select(PostGrowthValidation))).scalars().all())
    draft_ids = [int(v.draft_id) for v in validations]
    drafts: dict[int, Draft] = {}
    if draft_ids:
        for d in (await session.execute(select(Draft).where(Draft.id.in_(draft_ids)))).scalars().all():
            drafts[int(d.id)] = d

    for val in validations:
        stats.scanned += 1
        try:
            draft = drafts.get(int(val.draft_id))
            if draft is None:
                stats.skipped += 1
                continue
            segment = str(val.content_segment or "") or classify_from_draft_extras(
                draft.draft_extras, topic_bucket=val.topic_bucket
            )
            post = draft_to_post_dict(
                draft_id=int(draft.id),
                content=draft.content or "",
                sources=draft.sources or "[]",
                draft_extras=draft.draft_extras,
                editor_title=draft.editor_title,
                editor_summary=draft.editor_summary,
                content_segment=segment,
                format_profile=val.format_profile,
                virality_tier=val.virality_tier,
            )
            features = extract_editorial_features(post)
            if dry_run:
                stats.updated += 1
                continue
            await upsert_post_editorial_features(session, draft_id=int(draft.id), features=features)
            stats.updated += 1
        except Exception as exc:
            stats.errors += 1
            log_event(logger, "growth.editorial.backfill_error", draft_id=val.draft_id, error=repr(exc)[:120])

    if not dry_run:
        await session.flush()
    log_event(logger, "growth.editorial.backfill_complete", **stats.to_dict())
    return stats
