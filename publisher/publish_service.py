"""Publication pipeline callable from bot, scheduler, or future publisher workers."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum

from aiogram import Bot

from app.config import Settings
from db.repository import (
    approve_draft,
    get_draft_by_id,
    legacy_claim_pending_to_publishing,
    mark_draft_failed,
    mark_draft_published,
    mark_draft_publishing,
    reset_failed_draft_to_pending,
)
from db.models import DraftStatus
from db.session import session_scope
from publisher.publish_lock import publish_draft_lock
from publisher.telegram_publisher import publish_draft_to_channel
from dashboard.timeline import append_timeline_event
from utils.metrics import inc
from utils.observability import check_publish_trend, record_publish_duration
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_idem_memory: dict[str, tuple[int, int]] = {}
_idem_memory_lock = asyncio.Lock()


class PublishFlowOutcome(str, Enum):
    MISSING = "missing"
    DRY_RUN = "dry_run"
    ALREADY_HANDLED = "already_handled"
    APPROVE_DENIED = "approve_denied"
    CADENCE_DEFERRED = "cadence_deferred"
    SEND_FAILED = "send_failed"
    FINALIZE_MISMATCH = "finalize_mismatch"
    OK = "ok"


@dataclass(frozen=True)
class AdminPublishDraftResult:
    outcome: PublishFlowOutcome
    draft_content: str = ""
    draft_sources: str = ""
    channel_message_id: int | None = None
    error: str = ""


async def _idem_get_message_id(settings: Settings, key: str) -> int | None:
    from utils.redis_client import get_redis

    r = await get_redis()
    prefix = settings.job_queue_prefix.rstrip(":")
    redis_key = f"{prefix}:publish_idem:{key}"
    if r is not None:
        try:
            raw = await r.get(redis_key)
            if not raw:
                return None
            d = json.loads(raw)
            return int(d.get("message_id", 0)) or None
        except Exception:
            return None
    async with _idem_memory_lock:
        row = _idem_memory.get(key)
        return int(row[1]) if row else None


async def _idem_record_success(settings: Settings, key: str, draft_id: int, message_id: int) -> None:
    from utils.redis_client import get_redis

    r = await get_redis()
    prefix = settings.job_queue_prefix.rstrip(":")
    redis_key = f"{prefix}:publish_idem:{key}"
    payload = json.dumps({"draft_id": draft_id, "message_id": message_id}, separators=(",", ":"))
    if r is not None:
        try:
            await r.set(redis_key, payload, ex=86400 * 7)
        except Exception as exc:
            logger.warning("idempotency.redis_set_failed error=%s", repr(exc))
        return
    async with _idem_memory_lock:
        _idem_memory[key] = (draft_id, message_id)


def reset_idempotency_store_for_tests() -> None:
    _idem_memory.clear()


async def execute_admin_publication_flow(
    bot: Bot,
    settings: Settings,
    draft_id: int,
    *,
    idempotency_key: str | None = None,
) -> AdminPublishDraftResult:
    """
    Worker-ready publication: state transitions, optional idempotency, publish lock, Telegram send.
    """
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            return AdminPublishDraftResult(PublishFlowOutcome.MISSING)
        content = draft.content or ""
        sources = draft.sources or ""

    if settings.dry_run:
        log_event(logger, "publish.dry_run_skipped", draft_id=draft_id, recovery="dry_run_bypass")
        return AdminPublishDraftResult(
            PublishFlowOutcome.DRY_RUN,
            draft_content=content,
            draft_sources=sources,
        )

    if idempotency_key:
        prior_mid = await _idem_get_message_id(settings, idempotency_key)
        if prior_mid is not None:
            log_event(logger, "publish.idempotent_skip", draft_id=draft_id, idempotency_key=idempotency_key)
            return AdminPublishDraftResult(
                PublishFlowOutcome.ALREADY_HANDLED,
                draft_content=content,
                draft_sources=sources,
                channel_message_id=prior_mid,
            )

    async with publish_draft_lock(settings, draft_id) as lock_acquired:
        if not lock_acquired:
            return AdminPublishDraftResult(
                PublishFlowOutcome.ALREADY_HANDLED,
                draft_content=content,
                draft_sources=sources,
            )

        async with session_scope() as session:
            d = await get_draft_by_id(session, draft_id)
            if d is None:
                return AdminPublishDraftResult(PublishFlowOutcome.MISSING)
            if d.status == DraftStatus.FAILED.value:
                await reset_failed_draft_to_pending(session, draft_id)
            try:
                ex_obj = json.loads(d.draft_extras or "{}")
            except json.JSONDecodeError:
                ex_obj = {}
            brk = ex_obj.get("breaking") or {}
            is_breaking = bool(brk.get("is_breaking"))
            try:
                src_list = json.loads(d.sources or "[]")
            except json.JSONDecodeError:
                src_list = []
            chans = [str(s.get("channel") or "").strip().lower() for s in src_list if isinstance(s, dict)]
            dom = max(set(chans), key=chans.count) if chans else str(settings.source_channels[0]).lower()
            ci = ex_obj.get("cluster_intelligence") or {}
            ident = ci.get("event_identity") or {}
            topic_hint = str(ident.get("topic_hint") or "")
            from editorial.cadence import evaluate_publish_gate, topic_dedupe_key
            from editorial.policy import load_editorial_policy_bundle, resolve_effective_policy

            pol_eff, _ = resolve_effective_policy(load_editorial_policy_bundle(settings), dom)
            block, reasons = evaluate_publish_gate(
                settings,
                settings.runtime_state_dir,
                pol_eff,
                topic_key=topic_dedupe_key(topic_hint),
                is_breaking=is_breaking,
            )
            if block:
                inc("cadence_blocked_publish")
                log_event(
                    logger,
                    "publish.cadence_blocked",
                    draft_id=draft_id,
                    reasons=list(reasons),
                )
                append_timeline_event(
                    settings.runtime_state_dir,
                    "publish_cadence_blocked",
                    {"draft_id": draft_id, "reasons": list(reasons)[:16]},
                )
                return AdminPublishDraftResult(
                    PublishFlowOutcome.CADENCE_DEFERRED,
                    draft_content=d.content or "",
                    draft_sources=d.sources or "",
                    error=";".join(reasons)[:500],
                )
            approved = await approve_draft(session, draft_id)
            if not approved:
                d3 = await get_draft_by_id(session, draft_id)
                st = d3.status if d3 else ""
                if st in (DraftStatus.PUBLISHING.value, DraftStatus.PUBLISHED.value):
                    return AdminPublishDraftResult(
                        PublishFlowOutcome.ALREADY_HANDLED,
                        draft_content=content,
                        draft_sources=sources,
                    )
                return AdminPublishDraftResult(
                    PublishFlowOutcome.APPROVE_DENIED,
                    draft_content=content,
                    draft_sources=sources,
                )
            claimed = await mark_draft_publishing(session, draft_id) or await legacy_claim_pending_to_publishing(
                session, draft_id
            )
            if not claimed:
                return AdminPublishDraftResult(
                    PublishFlowOutcome.ALREADY_HANDLED,
                    draft_content=content,
                    draft_sources=sources,
                )
            draft = await get_draft_by_id(session, draft_id)
            if draft is None:
                return AdminPublishDraftResult(PublishFlowOutcome.MISSING)
            content = draft.content or ""
            sources = draft.sources or ""
            extras_json = draft.draft_extras or "{}"

        t_chunks = time.perf_counter()
        try:
            first_id = await publish_draft_to_channel(
                bot,
                settings,
                draft_id=draft_id,
                content=content,
                sources=sources,
                draft_extras_json=extras_json,
            )
        except BaseException as exc:
            logger.exception("Failed to publish draft %s: %s", draft_id, exc)
            log_event(logger, "publish.channel_send_failed", draft_id=draft_id, error=repr(exc))
            async with session_scope() as session:
                await mark_draft_failed(session, draft_id, reason=repr(exc))
            return AdminPublishDraftResult(PublishFlowOutcome.SEND_FAILED, error=repr(exc))

        chunks_duration = time.perf_counter() - t_chunks
        log_event(
            logger,
            "publish.telegram_chunks_duration_sec",
            draft_id=draft_id,
            duration_sec=round(chunks_duration, 4),
        )

        t_db = time.perf_counter()
        async with session_scope() as session:
            finalized = await mark_draft_published(session, draft_id, telegram_post_id=first_id)
            if not finalized:
                log_event(logger, "publish.finalize_state_mismatch", draft_id=draft_id)
                return AdminPublishDraftResult(
                    PublishFlowOutcome.FINALIZE_MISMATCH,
                    draft_content=content,
                    draft_sources=sources,
                    channel_message_id=first_id,
                )

        db_finalize_sec = time.perf_counter() - t_db
        log_event(
            logger,
            "publish.db_finalize_duration_sec",
            draft_id=draft_id,
            duration_sec=round(db_finalize_sec, 4),
        )

        publish_total = chunks_duration + db_finalize_sec
        record_publish_duration(publish_total)
        check_publish_trend(logger, settings, publish_total)

        inc("publishes")
        log_event(
            logger,
            "publish.success",
            draft_id=draft_id,
            channel_message_id=first_id,
        )
        append_timeline_event(
            settings.runtime_state_dir,
            "publication_ok",
            {"draft_id": draft_id, "channel_message_id": int(first_id)},
        )

        try:
            ex2 = json.loads(extras_json or "{}")
            th = str(((ex2.get("cluster_intelligence") or {}).get("event_identity") or {}).get("topic_hint") or "")
        except (json.JSONDecodeError, TypeError, AttributeError):
            th = ""
        from editorial.cadence import record_publish, topic_dedupe_key

        record_publish(settings.runtime_state_dir, topic_key=topic_dedupe_key(th))

        if idempotency_key:
            await _idem_record_success(settings, idempotency_key, draft_id, first_id)

        return AdminPublishDraftResult(
            PublishFlowOutcome.OK,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=first_id,
        )
