from __future__ import annotations

import difflib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import DraftCreatePayload
from db.models import Draft, DraftStatus, PublishedPost, RawPost
from utils.metrics import inc
from utils.structured_log import log_event
from utils.text_hash import normalize_text_for_match

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _merge_raw_post_media_extras(
    session: AsyncSession,
    *,
    raw_post_id: int,
    extras_json: str,
) -> None:
    """Backfill media on an existing raw post when collector re-downloads attachments."""
    try:
        incoming = json.loads(extras_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(incoming, dict):
        return
    new_media = incoming.get("media")
    if not isinstance(new_media, dict) or not str(new_media.get("local_path") or "").strip():
        return
    row = await session.get(RawPost, raw_post_id)
    if row is None:
        return
    try:
        current = json.loads(row.extras or "{}")
    except (json.JSONDecodeError, TypeError):
        current = {}
    if not isinstance(current, dict):
        current = {}
    existing_media = current.get("media")
    if isinstance(existing_media, dict) and str(existing_media.get("local_path") or "").strip():
        return
    current["media"] = new_media
    row.extras = json.dumps(current, ensure_ascii=False)
    log_event(
        logger,
        "raw_post.media_backfilled",
        raw_post_id=raw_post_id,
        message_id=new_media.get("message_id"),
    )


async def upsert_raw_post(
    session: AsyncSession,
    *,
    channel_name: str,
    message_id: int,
    text: str,
    created_at: datetime,
    extras_json: str = "{}",
) -> bool:
    """Insert raw post if missing. Returns True if inserted."""
    existing = await session.scalar(
        select(RawPost.id).where(
            RawPost.channel_name == channel_name,
            RawPost.message_id == message_id,
        )
    )
    if existing is not None:
        await _merge_raw_post_media_extras(
            session,
            raw_post_id=int(existing),
            extras_json=extras_json,
        )
        return False

    session.add(
        RawPost(
            channel_name=channel_name,
            message_id=message_id,
            text=text,
            extras=extras_json or "{}",
            created_at=created_at,
            collected_at=utcnow(),
        )
    )
    logger.debug("Stored new raw post %s:%s", channel_name, message_id)
    return True


async def fetch_unprocessed_raw_posts(session: AsyncSession, limit: int) -> list[RawPost]:
    stmt = (
        select(RawPost)
        .where(RawPost.processed_at.is_(None))
        .order_by(RawPost.created_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def mark_raw_posts_processed(session: AsyncSession, ids: list[int], when: datetime) -> None:
    if not ids:
        return
    await session.execute(update(RawPost).where(RawPost.id.in_(ids)).values(processed_at=when))


async def fetch_recent_drafts_for_dedupe(
    session: AsyncSession,
    *,
    limit: int = 24,
    not_older_than: datetime | None = None,
) -> list[tuple[str, str]]:
    stmt = select(Draft.content, Draft.content_hash)
    if not_older_than is not None:
        stmt = stmt.where(Draft.created_at >= not_older_than)
    stmt = stmt.order_by(Draft.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [(str(c), str(h)) for c, h in rows]


async def fetch_recent_published_for_dedupe(
    session: AsyncSession,
    *,
    limit: int = 24,
    not_older_than: datetime | None = None,
) -> list[tuple[str, str]]:
    stmt = (
        select(Draft.content, Draft.content_hash)
        .join(PublishedPost, PublishedPost.draft_id == Draft.id)
        .order_by(PublishedPost.published_at.desc())
        .limit(limit)
    )
    if not_older_than is not None:
        stmt = stmt.where(PublishedPost.published_at >= not_older_than)
    rows = (await session.execute(stmt)).all()
    return [(str(c), str(h)) for c, h in rows]


def draft_should_be_skipped_as_duplicate(
    *,
    new_content: str,
    new_hash: str,
    recent: list[tuple[str, str]],
    similarity_threshold: float,
) -> tuple[bool, str]:
    if not recent:
        return False, ""

    norm_new = normalize_text_for_match(new_content)
    for prev_content, prev_hash in recent:
        if prev_hash and prev_hash == new_hash:
            return True, "exact_hash_match"
        prev_norm = normalize_text_for_match(prev_content)
        if not prev_norm:
            continue
        ratio = difflib.SequenceMatcher(None, norm_new, prev_norm).ratio()
        if ratio >= similarity_threshold:
            return True, f"similar_content ratio={ratio:.3f}"

    return False, ""


async def create_draft(
    session: AsyncSession,
    *,
    content: str,
    content_hash: str,
    sources_payload: list[dict[str, Any]],
    status: str = DraftStatus.PENDING.value,
) -> Draft:
    payload = DraftCreatePayload.model_validate(
        {"content": content, "content_hash": content_hash, "sources": sources_payload}
    )
    normalized_sources = [s.model_dump(mode="json") for s in payload.sources]
    draft = Draft(
        content=payload.content,
        content_hash=payload.content_hash,
        sources=json.dumps(normalized_sources, ensure_ascii=False),
        status=status,
        created_at=utcnow(),
        draft_extras="{}",
        edit_history="[]",
        publish_attempts=0,
    )
    session.add(draft)
    await session.flush()
    inc("drafts_created")
    log_event(logger, "draft.created", draft_id=int(draft.id), status=draft.status)
    return draft


async def create_draft_and_mark_posts_processed(
    session: AsyncSession,
    *,
    content: str,
    content_hash: str,
    sources_payload: list[dict[str, Any]],
    raw_post_ids: list[int],
) -> Draft:
    """
    Atomically (single DB transaction via session_scope): validate sources, insert draft,
    mark raw posts processed. Rollback on any failure before commit.
    """
    payload = DraftCreatePayload.model_validate(
        {"content": content, "content_hash": content_hash, "sources": sources_payload}
    )
    normalized_sources = [s.model_dump(mode="json") for s in payload.sources]
    draft = Draft(
        content=payload.content,
        content_hash=payload.content_hash,
        sources=json.dumps(normalized_sources, ensure_ascii=False),
        status=DraftStatus.PENDING.value,
        created_at=utcnow(),
        draft_extras="{}",
        edit_history="[]",
        publish_attempts=0,
    )
    session.add(draft)
    await session.flush()
    await mark_raw_posts_processed(session, raw_post_ids, draft.created_at)
    inc("drafts_created")
    log_event(logger, "draft.created_with_raw_posts", draft_id=int(draft.id), raw_posts=len(raw_post_ids))
    return draft


async def get_draft_by_id(session: AsyncSession, draft_id: int) -> Draft | None:
    return await session.get(Draft, draft_id)


async def set_draft_admin_message(session: AsyncSession, draft_id: int, message_id: int) -> None:
    await session.execute(update(Draft).where(Draft.id == draft_id).values(admin_chat_message_id=message_id))


async def try_transition_draft_status(
    session: AsyncSession,
    *,
    draft_id: int,
    from_status: str,
    to_status: str,
) -> bool:
    res = await session.execute(
        update(Draft)
        .where(Draft.id == draft_id, Draft.status == from_status)
        .values(status=to_status)
    )
    rowcount = res.rowcount
    return bool(rowcount and rowcount > 0)


async def list_pending_drafts(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[Draft]:
    off = max(0, offset)
    stmt = (
        select(Draft)
        .where(Draft.status == DraftStatus.PENDING.value)
        .order_by(Draft.created_at.asc(), Draft.id.asc())
        .offset(off)
        .limit(max(1, min(limit, 200)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def list_recent_quality_failed_drafts(
    session: AsyncSession, *, limit: int = 15
) -> list[Draft]:
    """Recently-failed drafts blocked by editorial *quality* gates (not safety).

    Used only by the guaranteed publishing floor: when no clean pending draft is
    available (e.g. OpenAI is down and every fresh fallback summary is judged
    "low-signal"), the floor may still ship the freshest of these in safety-only
    mode so the channel never goes dark. Content-safety reasons (advertising,
    governance, language leaks) are excluded here and re-checked downstream.
    """
    safety_markers = (
        "advertis",
        "governance",
        "cjk",
        "language",
        "trust",
        "rumor",
        "contradiction",
    )
    stmt = (
        select(Draft)
        .where(Draft.status == DraftStatus.FAILED.value)
        .where(Draft.last_publish_error.like("final_gate:%"))
        .order_by(Draft.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[Draft] = []
    for d in rows:
        err = (d.last_publish_error or "").lower()
        if any(marker in err for marker in safety_markers):
            continue
        out.append(d)
    return out


def _channels_from_sources_json(sources: str | None) -> list[str]:
    if not sources:
        return []
    try:
        data = json.loads(sources)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for it in data:
        if isinstance(it, dict) and it.get("channel"):
            out.append(str(it.get("channel")).strip())
    return [x for x in out if x]


def _queue_sort_key_for_draft(d: Draft, mode: str) -> tuple:
    ex = _json_load_obj(d.draft_extras, {})
    if not isinstance(ex, dict):
        ex = {}
    pri = ex.get("priority") if isinstance(ex.get("priority"), dict) else {}
    brk = ex.get("breaking") if isinstance(ex.get("breaking"), dict) else {}
    pscore = float(pri.get("numeric_priority_score") or 0.0)
    bscore = float(brk.get("breaking_score") or 0.0)
    bflag = 1 if brk.get("is_breaking") else 0
    ts = d.created_at.timestamp() if d.created_at else 0.0
    did = int(d.id)
    if mode == "priority":
        return (-pscore, -bscore, ts, did)
    if mode == "breaking":
        return (-bflag, -bscore, -pscore, ts, did)
    return (ts, did)


async def list_pending_drafts_for_queue(
    session: AsyncSession,
    *,
    limit: int = 7,
    offset: int = 0,
    mode: str = "fifo",
    fetch_cap: int = 200,
) -> list[Draft]:
    """
    Pending drafts for moderation list views. Fetches a capped FIFO window then sorts in-process
    (deterministic, no heavy SQL).
    """
    cap = max(1, min(int(fetch_cap), 500))
    stmt = (
        select(Draft)
        .where(Draft.status == DraftStatus.PENDING.value)
        .order_by(Draft.created_at.asc(), Draft.id.asc())
        .limit(cap)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    mode_norm = (mode or "fifo").strip().lower()
    if mode_norm not in ("fifo", "priority", "breaking"):
        mode_norm = "fifo"
    rows.sort(key=lambda d: _queue_sort_key_for_draft(d, mode_norm))
    off = max(0, int(offset))
    lim = max(1, min(int(limit), 200))
    return rows[off : off + lim]


async def approve_draft(session: AsyncSession, draft_id: int) -> bool:
    """
    PENDING -> APPROVED. Idempotent: already APPROVED returns True without duplicate metrics.
    """
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        log_event(logger, "draft.approve_missing", draft_id=draft_id)
        return False
    if d.status == DraftStatus.APPROVED.value:
        return True
    if d.status != DraftStatus.PENDING.value:
        log_event(logger, "draft.approve_invalid_state", draft_id=draft_id, status=d.status)
        return False
    ok = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.PENDING.value,
        to_status=DraftStatus.APPROVED.value,
    )
    if ok:
        inc("drafts_approved")
        log_event(logger, "draft.approved", draft_id=draft_id)
        d2 = await get_draft_by_id(session, draft_id)
        if d2 is not None:
            d2.moderated_at = utcnow()
    return ok


async def mark_draft_publishing(session: AsyncSession, draft_id: int) -> bool:
    """APPROVED -> PUBLISHING. Returns False if already publishing (prevents duplicate channel sends)."""
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        return False
    if d.status == DraftStatus.PUBLISHING.value:
        return False
    ok = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.APPROVED.value,
        to_status=DraftStatus.PUBLISHING.value,
    )
    if ok:
        log_event(logger, "draft.mark_publishing", draft_id=draft_id)
        d2 = await get_draft_by_id(session, draft_id)
        if d2 is not None:
            d2.publish_attempts = int(d2.publish_attempts or 0) + 1
    return ok


async def legacy_claim_pending_to_publishing(session: AsyncSession, draft_id: int) -> bool:
    """PENDING -> PUBLISHING (legacy single-step claim for backward compatibility)."""
    return await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.PENDING.value,
        to_status=DraftStatus.PUBLISHING.value,
    )


async def reject_draft(session: AsyncSession, draft_id: int, *, reason: str = "") -> bool:
    """PENDING or APPROVED -> REJECTED."""
    d0 = await get_draft_by_id(session, draft_id)
    reject_channels = _channels_from_sources_json(d0.sources if d0 else None)
    for from_status in (DraftStatus.PENDING.value, DraftStatus.APPROVED.value):
        ok = await try_transition_draft_status(
            session,
            draft_id=draft_id,
            from_status=from_status,
            to_status=DraftStatus.REJECTED.value,
        )
        if ok:
            inc("drafts_rejected")
            log_event(logger, "draft.rejected_repo", draft_id=draft_id, from_status=from_status, reason=reason)
            d = await get_draft_by_id(session, draft_id)
            if d is not None:
                d.moderated_at = None
            try:
                from utils.source_reputation import record_reject_for_channels

                record_reject_for_channels(reject_channels)
            except Exception:
                pass
            try:
                from editorial.governance.ledger import append_decision

                append_decision(
                    runtime_dir=None,
                    decision_type="operator_reject",
                    outcome="rejected",
                    subject_type="draft",
                    subject_id=str(draft_id),
                    reason_codes=[reason[:80]] if reason else [],
                    operator_override={"channels": reject_channels[:12]},
                )
            except Exception:
                pass
            return True
    d = await get_draft_by_id(session, draft_id)
    if d is not None and d.status == DraftStatus.REJECTED.value:
        return True
    return False


async def mark_draft_published(session: AsyncSession, draft_id: int, *, telegram_post_id: int) -> bool:
    """PUBLISHING -> PUBLISHED + published_posts row (idempotent if already published)."""
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        return False
    if d.status == DraftStatus.PUBLISHED.value:
        return True
    ok = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.PUBLISHING.value,
        to_status=DraftStatus.PUBLISHED.value,
    )
    if not ok:
        return False
    existing = await session.scalar(select(PublishedPost.id).where(PublishedPost.draft_id == draft_id))
    if existing is None:
        await create_published_post(session, draft_id=draft_id, telegram_post_id=telegram_post_id)
    d2 = await get_draft_by_id(session, draft_id)
    if d2 is not None:
        d2.scheduled_publish_at = None
        d2.last_publish_error = None
    inc("drafts_published")
    log_event(logger, "draft.mark_published", draft_id=draft_id, telegram_post_id=telegram_post_id)
    try:
        from utils import editorial_analytics

        if d2 is not None:
            editorial_analytics.record_publish_attempt_count(int(d2.publish_attempts or 0))
            if d2.moderated_at is not None:
                editorial_analytics.record_moderation_publish_latency_sec(
                    max(0.0, (utcnow() - d2.moderated_at).total_seconds())
                )
    except Exception:
        pass
    try:
        from utils.source_reputation import record_publish_for_channels

        chans = _channels_from_sources_json(d.sources if d else None)
        record_publish_for_channels(chans)
    except Exception:
        pass
    try:
        from editorial.governance.ledger import append_decision

        append_decision(
            runtime_dir=None,
            decision_type="publish",
            outcome="published",
            subject_type="draft",
            subject_id=str(draft_id),
            publish={"telegram_post_id": telegram_post_id, "channels": chans[:12]},
        )
    except Exception:
        pass
    return True


async def reset_failed_draft_to_pending(session: AsyncSession, draft_id: int) -> bool:
    """FAILED -> PENDING (moderator retry after publish failure)."""
    ok = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.FAILED.value,
        to_status=DraftStatus.PENDING.value,
    )
    if ok:
        log_event(logger, "draft.failed_reset_to_pending", draft_id=draft_id)
    return ok


async def reopen_rejected_draft_to_pending(session: AsyncSession, draft_id: int) -> bool:
    """REJECTED/FAILED -> PENDING for an explicit operator override.

    The operator is the editor-in-chief: an editorial rejection must never be a
    dead end. This lets a manual Publish action re-open the draft so it can be
    approved and shipped (safety checks still apply downstream).
    """
    for from_status in (DraftStatus.REJECTED.value, DraftStatus.FAILED.value):
        ok = await try_transition_draft_status(
            session,
            draft_id=draft_id,
            from_status=from_status,
            to_status=DraftStatus.PENDING.value,
        )
        if ok:
            log_event(
                logger,
                "draft.operator_reopened_to_pending",
                draft_id=draft_id,
                from_status=from_status,
            )
            return True
    d = await get_draft_by_id(session, draft_id)
    return d is not None and d.status == DraftStatus.PENDING.value


async def mark_draft_failed(session: AsyncSession, draft_id: int, *, reason: str = "") -> bool:
    """PUBLISHING or APPROVED -> FAILED."""
    for from_status in (DraftStatus.PUBLISHING.value, DraftStatus.APPROVED.value):
        ok = await try_transition_draft_status(
            session,
            draft_id=draft_id,
            from_status=from_status,
            to_status=DraftStatus.FAILED.value,
        )
        if ok:
            inc("publish_failures")
            log_event(logger, "draft.mark_failed", draft_id=draft_id, from_status=from_status, reason=reason)
            d2 = await get_draft_by_id(session, draft_id)
            if d2 is not None:
                d2.last_publish_error = (reason or "")[:8000]
            return True
    d = await get_draft_by_id(session, draft_id)
    if d is not None and d.status == DraftStatus.FAILED.value:
        return True
    return False


async def rollback_draft_publishing_to_pending(session: AsyncSession, draft_id: int) -> bool:
    """PUBLISHING -> PENDING (dry-run / recovery)."""
    ok = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.PUBLISHING.value,
        to_status=DraftStatus.PENDING.value,
    )
    if ok:
        log_event(logger, "draft.rollback_publishing_to_pending", draft_id=draft_id)
        return True
    ok2 = await try_transition_draft_status(
        session,
        draft_id=draft_id,
        from_status=DraftStatus.APPROVED.value,
        to_status=DraftStatus.PENDING.value,
    )
    if ok2:
        log_event(logger, "draft.rollback_approved_to_pending", draft_id=draft_id)
    return ok2


async def create_published_post(session: AsyncSession, *, draft_id: int, telegram_post_id: int) -> PublishedPost:
    row = PublishedPost(
        draft_id=draft_id,
        telegram_post_id=telegram_post_id,
        published_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    return row


async def count_raw_posts(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(RawPost))
    return int(n or 0)


async def count_drafts(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(Draft))
    return int(n or 0)


async def count_unprocessed_raw_posts(session: AsyncSession) -> int:
    n = await session.scalar(
        select(func.count()).select_from(RawPost).where(RawPost.processed_at.is_(None))
    )
    return int(n or 0)


def _json_load_obj(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _append_edit_history(draft: Draft, action: str, **fields: Any) -> None:
    hist = _json_load_obj(draft.edit_history, [])
    if not isinstance(hist, list):
        hist = []
    entry: dict[str, Any] = {"ts": utcnow().isoformat(), "action": action}
    entry.update(fields)
    hist.append(entry)
    draft.edit_history = json.dumps(hist[-120:], ensure_ascii=False)


async def update_draft_title(session: AsyncSession, draft_id: int, *, title: str) -> bool:
    t = (title or "").strip()
    if not t:
        log_event(logger, "draft.edit_title_empty", draft_id=draft_id)
        return False
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        log_event(logger, "draft.edit_title_missing", draft_id=draft_id)
        return False
    if d.status in (DraftStatus.PUBLISHED.value, DraftStatus.REJECTED.value):
        log_event(logger, "draft.edit_title_bad_status", draft_id=draft_id, status=d.status)
        return False
    d.editor_title = t[:4000]
    _append_edit_history(d, "edit_title", value=t[:400])
    inc("draft_edits")
    log_event(logger, "draft.title_updated", draft_id=draft_id, len=len(t))
    return True


async def update_draft_content(session: AsyncSession, draft_id: int, *, content: str) -> bool:
    c = (content or "").strip()
    if not c:
        log_event(logger, "draft.edit_content_empty", draft_id=draft_id)
        return False
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        log_event(logger, "draft.edit_content_missing", draft_id=draft_id)
        return False
    if d.status in (DraftStatus.PUBLISHED.value, DraftStatus.REJECTED.value):
        log_event(logger, "draft.edit_content_bad_status", draft_id=draft_id, status=d.status)
        return False
    from utils.text_hash import sha256_hex

    d.content = c
    d.content_hash = sha256_hex(c)
    _append_edit_history(d, "edit_content", chars=len(c))
    inc("draft_edits")
    log_event(logger, "draft.content_updated", draft_id=draft_id, len=len(c))
    return True


async def update_draft_summary(session: AsyncSession, draft_id: int, *, summary: str) -> bool:
    s = (summary or "").strip()
    if not s:
        log_event(logger, "draft.edit_summary_empty", draft_id=draft_id)
        return False
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        log_event(logger, "draft.edit_summary_missing", draft_id=draft_id)
        return False
    if d.status in (DraftStatus.PUBLISHED.value, DraftStatus.REJECTED.value):
        log_event(logger, "draft.edit_summary_bad_status", draft_id=draft_id, status=d.status)
        return False
    d.editor_summary = s[:12000]
    _append_edit_history(d, "edit_summary", chars=len(s))
    inc("draft_edits")
    log_event(logger, "draft.summary_updated", draft_id=draft_id, len=len(s))
    return True


async def merge_draft_extras(session: AsyncSession, draft_id: int, patch: dict[str, Any]) -> bool:
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        return False
    cur = _json_load_obj(d.draft_extras, {})
    if not isinstance(cur, dict):
        cur = {}
    for k, v in patch.items():
        cur[str(k)] = v
    d.draft_extras = json.dumps(cur, ensure_ascii=False, sort_keys=True)
    if "moderation_note" in patch:
        prev = str(patch.get("moderation_note") or "")
        if prev.strip():
            _append_edit_history(d, "moderation_note", preview=prev.strip()[:240])
    if "policy_override_reason" in patch:
        pr = str(patch.get("policy_override_reason") or "")
        if pr.strip():
            _append_edit_history(d, "policy_override_reason", text=pr.strip()[:400])
    return True


async def schedule_draft_publish(session: AsyncSession, draft_id: int, *, when: datetime) -> bool:
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        log_event(logger, "draft.schedule_missing", draft_id=draft_id)
        return False
    if d.status not in (DraftStatus.PENDING.value, DraftStatus.APPROVED.value):
        log_event(logger, "draft.schedule_bad_status", draft_id=draft_id, status=d.status)
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    d.scheduled_publish_at = when.astimezone(timezone.utc)
    _append_edit_history(d, "schedule", at=d.scheduled_publish_at.isoformat())
    log_event(logger, "draft.scheduled", draft_id=draft_id, at=d.scheduled_publish_at.isoformat())
    return True


async def list_scheduled_drafts(session: AsyncSession, *, limit: int = 50) -> list[Draft]:
    lim = max(1, min(limit, 200))
    stmt = (
        select(Draft)
        .where(
            Draft.scheduled_publish_at.is_not(None),
            Draft.status.not_in(
                (DraftStatus.PUBLISHED.value, DraftStatus.REJECTED.value, DraftStatus.FAILED.value)
            ),
        )
        .order_by(Draft.scheduled_publish_at.asc().nulls_last(), Draft.id.asc())
        .limit(lim)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def list_due_scheduled_draft_ids(session: AsyncSession, *, limit: int = 3) -> list[int]:
    """APPROVED drafts with schedule time passed (moderated; no auto-approve of pending)."""
    lim = max(1, min(limit, 10))
    now = utcnow()
    stmt = (
        select(Draft.id)
        .where(
            Draft.status == DraftStatus.APPROVED.value,
            Draft.scheduled_publish_at.is_not(None),
            Draft.scheduled_publish_at <= now,
        )
        .order_by(Draft.scheduled_publish_at.asc(), Draft.id.asc())
        .limit(lim)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [int(x) for x in rows]


async def draft_duplicate_intel(
    session: AsyncSession,
    draft_id: int,
    *,
    similarity_threshold: float,
    window_hours: int = 72,
) -> dict[str, Any]:
    d = await get_draft_by_id(session, draft_id)
    if d is None:
        return {"severity": "none", "max_similarity_pct": 0.0, "related": [], "warning_lines": []}
    since = utcnow() - timedelta(hours=max(1, min(window_hours, 24 * 45)))
    stmt = (
        select(Draft.id, Draft.content, Draft.content_hash, Draft.created_at)
        .where(Draft.id != draft_id, Draft.created_at >= since)
        .order_by(Draft.created_at.desc())
        .limit(36)
    )
    rows = (await session.execute(stmt)).all()
    norm_new = normalize_text_for_match(d.content or "")
    related: list[dict[str, Any]] = []
    for oid, ocontent, ohash, ocreated in rows:
        oh = str(ohash or "")
        nh = str(d.content_hash or "")
        if oh and nh and oh == nh:
            pct = 100.0
        else:
            prev_norm = normalize_text_for_match(str(ocontent or ""))
            if not norm_new or not prev_norm:
                continue
            ratio = difflib.SequenceMatcher(None, norm_new, prev_norm).ratio()
            pct = round(ratio * 100.0, 2)
        if pct >= max(50.0, similarity_threshold * 100.0 - 5.0):
            related.append(
                {
                    "draft_id": int(oid),
                    "similarity_pct": pct,
                    "hash_prefix": str(oh)[:12],
                    "created_at": ocreated.isoformat() if ocreated else "",
                }
            )
    related.sort(key=lambda x: (-float(x["similarity_pct"]), int(x["draft_id"])))
    related = related[:8]
    max_pct = float(related[0]["similarity_pct"]) if related else 0.0
    severity = "none"
    if max_pct >= similarity_threshold * 100.0:
        severity = "high"
    elif max_pct >= similarity_threshold * 100.0 - 8.0:
        severity = "medium"
    elif max_pct >= 70.0:
        severity = "low"
    warnings: list[str] = []
    if severity == "high":
        warnings.append("Likely duplicate or very high overlap with a recent draft.")
    elif severity == "medium":
        warnings.append("Elevated similarity to recent drafts — verify before publishing.")
    return {
        "severity": severity,
        "max_similarity_pct": max_pct,
        "related": related,
        "warning_lines": warnings,
    }


async def search_drafts_operational(
    session: AsyncSession,
    *,
    topic_substr: str | None = None,
    entity_substr: str | None = None,
    fingerprint_substr: str | None = None,
    suppression_reason_substr: str | None = None,
    status: str | None = None,
    limit: int = 30,
) -> list[Draft]:
    """Read-only helper for ops UI / bot: substring search across body, extras, sources."""
    lim = max(1, min(limit, 100))
    preds: list[Any] = []
    st = (status or "").strip().lower()
    if st:
        preds.append(Draft.status == st)

    or_parts: list[Any] = []
    topic = (topic_substr or "").strip()
    entity = (entity_substr or "").strip()
    fp = (fingerprint_substr or "").strip()
    sup = (suppression_reason_substr or "").strip()

    if topic:
        q = f"%{topic}%"
        or_parts.extend(
            [
                Draft.content.ilike(q),
                Draft.editor_title.ilike(q),
                Draft.editor_summary.ilike(q),
            ]
        )
    if entity:
        q = f"%{entity}%"
        or_parts.extend(
            [
                Draft.content.ilike(q),
                Draft.draft_extras.ilike(q),
                Draft.sources.ilike(q),
            ]
        )
    if fp:
        q = f"%{fp}%"
        or_parts.extend([Draft.draft_extras.ilike(q), Draft.content_hash.like(q)])
    if sup:
        q = f"%{sup}%"
        or_parts.append(Draft.draft_extras.ilike(q))

    if not preds and not or_parts:
        return []

    stmt = select(Draft).order_by(Draft.id.desc()).limit(lim)
    if preds and or_parts:
        stmt = stmt.where(and_(*preds, or_(*or_parts)))
    elif preds:
        stmt = stmt.where(and_(*preds))
    else:
        stmt = stmt.where(or_(*or_parts))

    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
