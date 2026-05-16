from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Draft, DraftStatus, RawPost

logger = logging.getLogger(__name__)


async def delete_old_processed_raw_posts(session: AsyncSession, *, older_than: datetime) -> int:
    """Remove processed raw posts with processed_at strictly before cutoff."""
    res = await session.execute(
        delete(RawPost).where(
            RawPost.processed_at.is_not(None),
            RawPost.processed_at < older_than,
        )
    )
    n = int(res.rowcount or 0)
    if n:
        logger.info("Retention: deleted %s old processed raw_posts", n)
    return n


async def delete_old_rejected_drafts(session: AsyncSession, *, older_than: datetime) -> int:
    res = await session.execute(
        delete(Draft).where(
            Draft.status == DraftStatus.REJECTED.value,
            Draft.created_at < older_than,
        )
    )
    n = int(res.rowcount or 0)
    if n:
        logger.info("Retention: deleted %s old rejected drafts", n)
    return n
