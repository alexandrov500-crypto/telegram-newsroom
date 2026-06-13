"""Inline wire-fast publish — ship fresh fastlane drafts in the same pipeline tick."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def wire_fast_publish_enabled() -> bool:
    raw = os.getenv("WIRE_FAST_PUBLISH_ENABLED", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"off", "false", "0", "no"}:
        return False
    try:
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        return news_channel_beat_enabled()
    except Exception:
        return False


def wire_fast_skip_ai_review() -> bool:
    return os.getenv("WIRE_FAST_PUBLISH_SKIP_AI_REVIEW", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _dominant_source(sources_json: str | None) -> str:
    if not sources_json:
        return ""
    try:
        data = json.loads(sources_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, list):
        return ""
    counts: dict[str, int] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        ch = str(row.get("channel") or "").strip().lower()
        if not ch:
            continue
        key = ch if ch.startswith("@") else f"@{ch.lstrip('@')}"
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    return max(counts.keys(), key=lambda k: (counts[k], k))


def _is_fastlane_draft(sources_json: str | None) -> bool:
    from app.growth.wire_freshness import is_fastlane_source

    src = _dominant_source(sources_json)
    return bool(src) and is_fastlane_source(src)


async def try_wire_inline_publish(
    bot: Any,
    settings: Any,
    draft_id: int,
    *,
    sources_json: str | None = None,
    extras_json: str | None = None,
) -> bool:
    """
    Publish immediately when draft is fresh and from a fastlane wire source.
    Returns True if a message was sent to the channel.
    """
    if not wire_fast_publish_enabled():
        return False

    from app.growth.wire_freshness import draft_age_minutes, wire_freshness_max_minutes
    from db.repository import get_draft_by_id
    from db.session import session_scope
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            return False
        age = draft_age_minutes(draft)
        src_json = sources_json or str(getattr(draft, "sources", "") or "[]")
        if age > wire_freshness_max_minutes():
            log_event(logger, "wire_fast.skipped", draft_id=draft_id, reason="stale", age_min=round(age, 1))
            return False
        if not _is_fastlane_draft(src_json):
            log_event(logger, "wire_fast.skipped", draft_id=draft_id, reason="not_fastlane")
            return False

    res = await execute_admin_publication_flow(
        bot,
        settings,
        draft_id,
        bypass_cadence=True,
        bypass_leadership=True,
    )
    if res.outcome is PublishFlowOutcome.OK:
        log_event(
            logger,
            "wire_fast.published",
            draft_id=draft_id,
            message_id=res.channel_message_id,
            age_min=round(age, 1),
            source=_dominant_source(src_json),
        )
        return True
    log_event(
        logger,
        "wire_fast.blocked",
        draft_id=draft_id,
        outcome=res.outcome.value,
        error=(res.error or "")[:120],
    )
    return False
