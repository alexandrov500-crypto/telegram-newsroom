"""Backfill content_segment on post_growth_validation rows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.segments.content_segments import classify_content_segment, classify_from_draft_extras
from db.models import Draft, PostGrowthValidation
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass
class SegmentBackfillStats:
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


async def backfill_content_segments(
    session: AsyncSession,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> SegmentBackfillStats:
    stats = SegmentBackfillStats(dry_run=dry_run)
    rows = list((await session.execute(select(PostGrowthValidation))).scalars().all())
    draft_ids = [int(r.draft_id) for r in rows]
    drafts: dict[int, Draft] = {}
    if draft_ids:
        draft_rows = list(
            (await session.execute(select(Draft).where(Draft.id.in_(draft_ids)))).scalars().all()
        )
        drafts = {int(d.id): d for d in draft_rows}

    for row in rows:
        stats.scanned += 1
        try:
            if row.content_segment and row.content_segment != "general_news" and not force:
                stats.skipped += 1
                continue
            draft = drafts.get(int(row.draft_id))
            segment = ""
            if draft is not None:
                segment = classify_content_segment(
                    {
                        "draft_extras": draft.draft_extras,
                        "topic_bucket": row.topic_bucket,
                        "category": row.topic_bucket,
                    }
                )
            if not segment or segment == "general_news":
                segment = classify_from_draft_extras(
                    draft.draft_extras if draft else None,
                    topic_bucket=row.topic_bucket,
                )
            if not dry_run:
                row.content_segment = str(segment)[:32]
                stats.updated += 1
            else:
                stats.updated += 1
        except Exception as exc:
            stats.errors += 1
            log_event(logger, "growth.segment.backfill_error", draft_id=row.draft_id, error=repr(exc)[:120])

    if not dry_run:
        await session.flush()
    log_event(logger, "growth.segment.backfill_complete", **stats.to_dict())
    return stats
