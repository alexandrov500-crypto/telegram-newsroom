"""Automatic retry for transient publish failures."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from aiogram import Bot

from db.reliability_repository import bump_failed_draft_after_attempt, enqueue_failed_draft, list_due_failed_drafts, mark_failed_draft_terminal
from db.repository import get_draft_by_id, reset_failed_draft_to_pending
from db.session import session_scope
from publisher.publish_service import AdminPublishDraftResult, PublishFlowOutcome, execute_admin_publication_flow
from utils.error_classifier import classify_runtime_error
from utils.operational_context import get_operational_log_fields, set_correlation_id
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_NON_RETRY_PATTERNS = re.compile(
    r"(desk_reject|editorial_reject|hallucination|duplicate|cadence_blocked|"
    r"quality_below|safety|not_retryable|finalize_state|final_gate|public_output_lock|"
    r"governance:|low_trust|sensational_tone|max_retries_exceeded|manual_review)",
    re.I,
)


def max_retry_count() -> int:
    raw = os.getenv("FAILED_DRAFT_MAX_RETRIES", "5").strip()
    try:
        return max(1, min(int(raw), 20))
    except ValueError:
        return 5


def is_publish_failure_retryable(*, reason: str, error_category: str = "") -> bool:
    r = (reason or "").strip()
    if not r:
        return False
    if _NON_RETRY_PATTERNS.search(r):
        return False
    if error_category in ("validation",):
        return False
    low = r.lower()
    if any(x in low for x in ("timeout", "timed out", "network", "connection reset", "floodwait")):
        return True
    if "locked" in low and ("sqlite" in low or "database" in low):
        return True
    ce = classify_runtime_error(Exception(r))
    if ce.category == "validation":
        return False
    if "cadence" in low or "duplicate" in low:
        if "cadence_deferred" in low or "cadence / quiet" in low:
            return True
        return False
    return ce.retryable or ce.category in ("telegram", "network", "openai", "database", "scheduler")


async def record_publish_failure(
    draft_id: int,
    *,
    reason: str,
    correlation_id: str = "",
) -> None:
    ce = classify_runtime_error(Exception(reason))
    if not is_publish_failure_retryable(reason=reason, error_category=ce.category):
        await mark_failed_draft_terminal(draft_id, reason=f"non_retryable:{reason[:200]}")
        return
    await enqueue_failed_draft(
        draft_id,
        error=reason,
        error_category=ce.category,
        correlation_id=correlation_id,
        retryable=True,
    )


async def run_failed_draft_retry_batch(
    bot: Bot,
    settings: Any,
    *,
    limit: int = 4,
) -> dict[str, Any]:
    """Retry due failed drafts (heartbeat / cron)."""
    from app.operational_mode import load_operational_mode, publish_allowed

    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    if not publish_allowed(op_mode, settings):
        return {"skipped": "publish_not_allowed", "mode": op_mode.value}

    due = await list_due_failed_drafts(limit=limit)
    outcomes: list[dict[str, Any]] = []
    for row in due:
        if int(row.retry_count) >= max_retry_count():
            await mark_failed_draft_terminal(int(row.draft_id), reason="max_retries_exceeded")
            continue
        cid = (row.correlation_id or "").strip()
        tok = set_correlation_id(cid) if cid else None
        try:
            async with session_scope() as session:
                d = await get_draft_by_id(session, int(row.draft_id))
                if d is None:
                    await mark_failed_draft_terminal(int(row.draft_id), reason="draft_missing")
                    continue
                await reset_failed_draft_to_pending(session, int(row.draft_id))
            res: AdminPublishDraftResult = await execute_admin_publication_flow(
                bot,
                settings,
                int(row.draft_id),
                idempotency_key=f"retry:{row.draft_id}:{row.retry_count}",
                bypass_cadence=True,
            )
            ok = res.outcome == PublishFlowOutcome.OK
            if ok:
                await bump_failed_draft_after_attempt(int(row.draft_id), success=True)
            else:
                err = res.error or res.outcome.value
                if res.outcome == PublishFlowOutcome.CADENCE_DEFERRED:
                    await bump_failed_draft_after_attempt(int(row.draft_id), success=False, error=err)
                elif not is_publish_failure_retryable(reason=err):
                    await mark_failed_draft_terminal(int(row.draft_id), reason=err[:500])
                else:
                    await bump_failed_draft_after_attempt(int(row.draft_id), success=False, error=err)
            outcomes.append({"draft_id": row.draft_id, "outcome": res.outcome.value})
            log_event(
                logger,
                "failed_draft.retry_attempt",
                draft_id=row.draft_id,
                outcome=res.outcome.value,
                correlation_id=cid or get_operational_log_fields().get("correlation_id"),
            )
            try:
                from app.observability.runtime_health import record_retry_event

                record_retry_event()
            except Exception:
                pass
        except Exception as exc:
            await bump_failed_draft_after_attempt(int(row.draft_id), success=False, error=repr(exc))
            outcomes.append({"draft_id": row.draft_id, "error": repr(exc)[:200]})
        finally:
            if tok is not None:
                from utils.operational_context import reset_correlation_id

                reset_correlation_id(tok)
    return {"attempted": len(outcomes), "outcomes": outcomes}
