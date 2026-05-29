"""Publication pipeline callable from bot, scheduler, or future publisher workers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

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
from publisher.publish_trace import PublishTraceTimer, log_publish_trace
from publisher.telegram_publisher import publish_draft_to_channel
from dashboard.timeline import append_timeline_event
from utils.metrics import inc
from utils.observability import check_publish_trend, record_publish_duration
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_idem_memory: dict[str, tuple[int, int]] = {}
_idem_memory_lock = asyncio.Lock()


def _final_gate_state_path(runtime_dir: str) -> Path:
    from pathlib import Path

    return Path(runtime_dir).expanduser().resolve() / "final_publish_gate_state.json"


def _record_final_gate_block(runtime_dir: str, reason: str) -> int:
    import json
    import time

    p = _final_gate_state_path(runtime_dir)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}
    c = int(data.get("block_count") or 0) + 1
    data["block_count"] = c
    data["last_reason"] = reason[:240]
    data["last_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return c


async def publish_allowed_final_check(
    *,
    settings: Settings,
    draft_id: int,
    idempotency_key: str,
    draft_extras_json: str | None,
    operator_approved: bool = False,
) -> tuple[bool, str]:
    from app.ops.execution_gates import evaluate_publish_gate
    from app.ops.live_rollback import rollback_active
    from app.observability.runtime_protection import protection_payload
    from app.observability.execution_graph_report import build_execution_graph_report
    from app.observability.prepublic_qa import prepublic_qa_enabled
    from utils.database_url import sqlite_path_from_url

    # core publish gate (execution graph/runtime/incident/rollout)
    gate = evaluate_publish_gate(settings, trace=False)
    if not gate.allowed:
        return False, f"base_gate:{gate.reason}"

    if rollback_active(settings.runtime_state_dir):
        return False, "live_rollback_active"

    prot = protection_payload(settings.runtime_state_dir)
    if str(prot.get("current_state") or "").lower() == "critical":
        return False, "runtime_critical"

    starvation_recovery = False
    try:
        from app.editorial.desk_starvation import desk_threshold_context

        starvation_recovery = desk_threshold_context().publish_starvation_detected
    except Exception:
        pass

    # execution graph: recent window only (stale pre-outage traces must not block recovery)
    graph_window = int(os.getenv("PUBLISH_EXEC_GRAPH_WINDOW", "12"))
    dbp = sqlite_path_from_url(settings.database_url)
    eg = build_execution_graph_report(
        db_path=Path(dbp) if dbp and Path(dbp).is_file() else None,
        runtime_dir=Path(settings.runtime_state_dir),
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
        window_ticks=graph_window,
    )
    graph_ok = float(eg.get("consistency_rate") or 0) >= 1.0 or int(eg.get("trace_samples") or 0) < 3
    if not graph_ok and not starvation_recovery and not operator_approved:
        return False, "execution_graph_inconsistent"
    if not graph_ok and (starvation_recovery or operator_approved):
        log_event(
            logger,
            "publish.final_gate_starvation_bypass",
            draft_id=draft_id,
            recovery="execution_graph_check_skipped",
            consistency_rate=eg.get("consistency_rate"),
            trace_samples=eg.get("trace_samples"),
            operator_approved=operator_approved,
        )

    # QA mode safety rule: require moderation chat configured.
    if prepublic_qa_enabled() and not getattr(settings, "moderation_chat_id", None):
        return False, "prepublic_qa_without_moderation_chat"

    # dedup idempotency not seen before
    from app.reliability.idempotency import is_idempotency_processed

    if is_idempotency_processed(settings.runtime_state_dir, idempotency_key):
        return False, "idempotency_already_processed"

    # ensure draft not already published
    try:
        import sqlite3

        if dbp and Path(dbp).is_file():
            conn = sqlite3.connect(dbp, timeout=4.0)
            row = conn.execute(
                "SELECT COUNT(*) FROM published_posts WHERE draft_id = ?",
                (int(draft_id),),
            ).fetchone()
            conn.close()
            if int((row or [0])[0] or 0) > 0:
                return False, "draft_already_published"
    except Exception:
        pass
    return True, "ok"


async def _publish_attempt_number(draft_id: int) -> int:
    try:
        from db.reliability_repository import get_failed_draft_row

        row = await get_failed_draft_row(draft_id)
        if row is not None:
            return int(row.retry_count or 0) + 1
    except Exception:
        pass
    return 1


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
    bypass_cadence: bool = False,
    bypass_leadership: bool = False,
    floor_publish: bool = False,
    operator_override: bool = False,
) -> AdminPublishDraftResult:
    """Publication entry — enforced via pipeline execution wrapper."""
    from scheduler.runtime_context import get_pipeline_context
    from app.state.pipeline_execution_wrapper import execute_pipeline_publish

    ctx = get_pipeline_context()

    async def _run() -> AdminPublishDraftResult:
        return await _execute_admin_publication_flow_impl(
            bot,
            settings,
            draft_id,
            idempotency_key=idempotency_key,
            bypass_cadence=bypass_cadence,
            bypass_leadership=bypass_leadership,
            floor_publish=floor_publish,
            operator_override=operator_override,
        )

    out = await execute_pipeline_publish(ctx, draft_id=draft_id, publish_fn=_run)
    if out is None:
        return AdminPublishDraftResult(
            PublishFlowOutcome.APPROVE_DENIED,
            error="pipeline_wrapper_blocked_publish",
        )
    return out


async def _execute_admin_publication_flow_impl(
    bot: Bot,
    settings: Settings,
    draft_id: int,
    *,
    idempotency_key: str | None = None,
    bypass_cadence: bool = False,
    bypass_leadership: bool = False,
    floor_publish: bool = False,
    operator_override: bool = False,
) -> AdminPublishDraftResult:
    """
    Worker-ready publication: state transitions, optional idempotency, publish lock, Telegram send.

    ``floor_publish`` is the guaranteed publishing floor: it bypasses cadence /
    leadership and runs the final gate in safety-only mode so a trustworthy
    item ships even when editorial/marketing experiments would reject every
    draft. Content-safety checks (advertising, governance, trust) still apply.

    ``operator_override`` is an explicit human Publish action: the operator is
    the editor-in-chief, so an editorial rejection must not be a dead end. It
    re-opens a rejected/failed draft and runs the gate in safety-only mode
    (advertising/governance/trust still enforced).
    """
    from app.state.pipeline_execution_wrapper import require_pipeline_wrapper_active

    require_pipeline_wrapper_active("publish_flow")
    from app.pipeline_debug import debug_bypass_publish_gates, pipeline_debug_active
    from ops.resilience.leadership import require_publish_leadership
    from ops.resilience.publish_journal import (
        append_journal,
        find_by_idempotency_key,
        find_finalized_for_draft,
        new_publish_tx_id,
    )

    tx_id = new_publish_tx_id()
    idem_key = idempotency_key or f"draft:{draft_id}"
    publish_attempt = await _publish_attempt_number(draft_id)

    from app.pipeline_debug import debug_bypass_publish_gates, pipeline_debug_active
    from app.recovery.pipeline_overrides import is_force_publish_bypass, is_minimal_pipeline_mode

    debug_pub = pipeline_debug_active(settings)
    recovery_pub = is_minimal_pipeline_mode() or is_force_publish_bypass()
    bypass_cadence = (
        bypass_cadence or debug_bypass_publish_gates(settings) or recovery_pub or floor_publish or operator_override
    )
    bypass_leadership = (
        bypass_leadership or debug_bypass_publish_gates(settings) or recovery_pub or floor_publish or operator_override
    )
    # W1: floor must NOT bypass premium editorial gate — operator override only.
    safety_only_gate = operator_override and not floor_publish

    try:
        from app.reliability.publish_watchdog import check_publish_watchdog

        if not bypass_cadence:
            wd = await check_publish_watchdog(draft_id)
            if not wd.allowed:
                log_event(
                    logger,
                    "publish.watchdog_blocked",
                    draft_id=draft_id,
                    reason=wd.reason,
                    retry_count=wd.retry_count,
                )
                inc("publish_watchdog_blocked_total")
                return AdminPublishDraftResult(
                    PublishFlowOutcome.APPROVE_DENIED,
                    error=wd.reason,
                )
    except Exception:
        pass
    trace_timer = PublishTraceTimer()
    log_publish_trace(
        event="started",
        draft_id=draft_id,
        publish_attempt=publish_attempt,
        idempotency_key=idem_key,
        tx_id=tx_id,
    )
    if recovery_pub:
        log_event(
            logger,
            "publish.recovery_bypass",
            draft_id=draft_id,
            force_publish_bypass=is_force_publish_bypass(),
            minimal_mode=is_minimal_pipeline_mode(),
        )

    log_event(
        logger,
        "publish.attempted",
        draft_id=draft_id,
        idempotency_key=idem_key,
        pipeline_debug=debug_pub,
        bypass_cadence=bypass_cadence,
        bypass_leadership=bypass_leadership,
    )

    from app.observability.publish_audit import log_publish_audit, resolve_publish_mode
    from app.ops.execution_gates import evaluate_publish_gate

    publish_mode = resolve_publish_mode(settings)
    gate = evaluate_publish_gate(settings)
    if not gate.allowed:
        log_event(
            logger,
            "publish.blocked",
            draft_id=draft_id,
            reason=gate.reason,
            layer=gate.layer,
        )
        log_event(logger, "publish.failed", draft_id=draft_id, reason=gate.reason)
        log_publish_audit(
            draft_id=draft_id,
            publish_decision="blocked",
            publish_mode=publish_mode,
            extra={"block_reason": gate.reason, "gate_layer": gate.layer},
        )
        return AdminPublishDraftResult(
            PublishFlowOutcome.APPROVE_DENIED,
            error=gate.reason,
        )
    log_publish_audit(
        draft_id=draft_id,
        publish_decision="allowed",
        publish_mode=publish_mode,
        extra={"gate_layer": gate.layer},
    )
    try:
        from app.observability.prepublic_qa import prepublic_qa_enabled, record_publish_decision_explanation

        if prepublic_qa_enabled():
            record_publish_decision_explanation(
                settings.runtime_state_dir,
                draft_id=draft_id,
                decision="allowed",
                detail={"gate_layer": gate.layer, "publish_mode": publish_mode},
            )
    except Exception:
        pass
    if not bypass_leadership and not require_publish_leadership(settings.runtime_state_dir):
        log_event(logger, "publish.blocked_no_leadership", draft_id=draft_id)
        log_event(logger, "publish.failed", draft_id=draft_id, reason="no_leadership")
        return AdminPublishDraftResult(
            PublishFlowOutcome.ALREADY_HANDLED,
            error="publish_leader_not_held",
        )

    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            return AdminPublishDraftResult(PublishFlowOutcome.MISSING)
        content = draft.content or ""
        sources = draft.sources or ""

    finalized = find_finalized_for_draft(settings.runtime_state_dir, draft_id)
    if finalized and int(finalized.get("channel_message_id") or 0):
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="idempotent_replay",
            idempotency_key=idem_key,
            channel_message_id=int(finalized["channel_message_id"]),
        )
        return AdminPublishDraftResult(
            PublishFlowOutcome.ALREADY_HANDLED,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=int(finalized["channel_message_id"]),
        )

    from app.reliability.idempotency import is_idempotency_processed, mark_idempotency_processed

    if is_idempotency_processed(settings.runtime_state_dir, idem_key):
        prior = await _idem_get_message_id(settings, idem_key)
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="idempotent_replay",
            idempotency_key=idem_key,
            channel_message_id=prior,
        )
        return AdminPublishDraftResult(
            PublishFlowOutcome.ALREADY_HANDLED,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=prior,
        )

    journal_idem = find_by_idempotency_key(settings.runtime_state_dir, idem_key)
    if journal_idem and int(journal_idem.get("channel_message_id") or 0):
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="idempotent_replay",
            idempotency_key=idem_key,
            channel_message_id=int(journal_idem["channel_message_id"]),
        )
        return AdminPublishDraftResult(
            PublishFlowOutcome.ALREADY_HANDLED,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=int(journal_idem["channel_message_id"]),
        )

    append_journal(
        settings.runtime_state_dir,
        tx_id=tx_id,
        draft_id=draft_id,
        state="initiated",
        idempotency_key=idem_key,
    )

    if settings.dry_run and not debug_pub:
        log_event(logger, "publish.dry_run_skipped", draft_id=draft_id, recovery="dry_run_bypass")
        log_event(logger, "publish.failed", draft_id=draft_id, reason="dry_run")
        return AdminPublishDraftResult(
            PublishFlowOutcome.DRY_RUN,
            draft_content=content,
            draft_sources=sources,
        )

    prior_mid = await _idem_get_message_id(settings, idem_key)
    if prior_mid is not None:
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="idempotent_replay",
            idempotency_key=idem_key,
            channel_message_id=prior_mid,
        )
        log_event(logger, "publish.idempotent_skip", draft_id=draft_id, idempotency_key=idem_key)
        return AdminPublishDraftResult(
            PublishFlowOutcome.ALREADY_HANDLED,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=prior_mid,
        )

    final_ok, final_reason = await publish_allowed_final_check(
        settings=settings,
        draft_id=draft_id,
        idempotency_key=idem_key,
        draft_extras_json="",
        operator_approved=bypass_cadence,
    )
    if not final_ok:
        cnt = _record_final_gate_block(settings.runtime_state_dir, final_reason)
        log_event(
            logger,
            "publish_blocked_final_gate",
            draft_id=draft_id,
            reason=final_reason,
            block_count=cnt,
        )
        if cnt >= int(os.getenv("FINAL_GATE_ALERT_REPEAT", "3")):
            try:
                from ops.operator_notifications import enqueue_operator_notification

                enqueue_operator_notification(
                    settings.runtime_state_dir,
                    kind="publish_blocked_final_gate",
                    severity="critical",
                    message=f"Final publish gate repeatedly blocked ({cnt}): {final_reason}",
                    fields={"draft_id": draft_id, "reason": final_reason, "block_count": cnt},
                )
            except Exception:
                pass
        return AdminPublishDraftResult(
            PublishFlowOutcome.APPROVE_DENIED,
            draft_content=content,
            draft_sources=sources,
            error=final_reason,
        )

    async with publish_draft_lock(settings, draft_id) as lock_acquired:
        if not lock_acquired:
            return AdminPublishDraftResult(
                PublishFlowOutcome.ALREADY_HANDLED,
                draft_content=content,
                draft_sources=sources,
            )
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="lock_acquired",
            idempotency_key=idem_key,
        )

        async with session_scope() as session:
            d = await get_draft_by_id(session, draft_id)
            if d is None:
                return AdminPublishDraftResult(PublishFlowOutcome.MISSING)
            if d.status == DraftStatus.REJECTED.value and operator_override:
                from db.repository import reopen_rejected_draft_to_pending

                await reopen_rejected_draft_to_pending(session, draft_id)
                log_event(logger, "publish.operator_reopened_rejected", draft_id=draft_id)
            elif d.status == DraftStatus.FAILED.value:
                await reset_failed_draft_to_pending(session, draft_id)
            elif d.status == DraftStatus.PUBLISHING.value and bypass_cadence:
                from app.reliability.stuck_publishing_recovery import rollback_stale_publishing_draft

                outcome = await rollback_stale_publishing_draft(
                    session,
                    draft_id,
                    force=True,
                )
                if outcome == "reconciled":
                    d2 = await get_draft_by_id(session, draft_id)
                    if d2 and d2.status == DraftStatus.PUBLISHED.value:
                        return AdminPublishDraftResult(
                            PublishFlowOutcome.ALREADY_HANDLED,
                            draft_content=d.content or "",
                            draft_sources=d.sources or "",
                        )
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
                content=d.content or "",
            )
            from app.editorial.final_publish_gate import evaluate_final_publish_gate

            gate = evaluate_final_publish_gate(
                content=d.content or "",
                sources=d.sources or "[]",
                draft_extras_json=d.draft_extras,
                settings=settings,
                operator_approved=bypass_cadence,
                draft_id=draft_id,
                safety_only=safety_only_gate,
            )
            if not gate.allowed:
                inc("final_publish_gate_blocked_total")
                log_event(
                    logger,
                    "publish.final_gate_blocked",
                    draft_id=draft_id,
                    reason=gate.reason,
                    manual=gate.manual_review_required,
                    permanent=gate.permanent_block,
                )
                if gate.permanent_block:
                    await mark_draft_failed(session, draft_id, reason=f"final_gate:{gate.reason}")
                return AdminPublishDraftResult(
                    PublishFlowOutcome.APPROVE_DENIED,
                    draft_content=d.content or "",
                    draft_sources=d.sources or "",
                    error=gate.reason,
                )

            if block and not bypass_cadence:
                inc("cadence_blocked_publish")
                append_journal(
                    settings.runtime_state_dir,
                    tx_id=tx_id,
                    draft_id=draft_id,
                    state="cadence_blocked",
                    idempotency_key=idem_key,
                    extra={"reasons": list(reasons)[:16]},
                )
                log_event(
                    logger,
                    "publish.cadence_blocked",
                    draft_id=draft_id,
                    reasons=list(reasons),
                )
                log_event(logger, "publish.failed", draft_id=draft_id, reason="cadence_blocked", reasons=list(reasons)[:8])
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

            try:
                from app.flywheel.pipeline import evaluate_pre_publish_editorial

                topic_bucket = str(ex_obj.get("category") or topic_hint or "general")
                w3 = evaluate_pre_publish_editorial(
                    d.content or "",
                    settings=settings,
                    runtime_dir=settings.runtime_state_dir,
                    vertical=topic_bucket,
                    is_breaking=is_breaking,
                )
                if not w3.allowed and not bypass_cadence and not operator_override:
                    inc("editorial_identity_blocked_total")
                    log_event(
                        logger,
                        "publish.w3_editorial_blocked",
                        draft_id=draft_id,
                        reason=w3.reason,
                        routing=w3.routing_reason,
                    )
                    return AdminPublishDraftResult(
                        PublishFlowOutcome.APPROVE_DENIED,
                        draft_content=d.content or "",
                        draft_sources=d.sources or "",
                        error=f"w3:{w3.reason}",
                    )
            except Exception as w3_exc:
                log_event(logger, "publish.w3_check_skipped", draft_id=draft_id, error=repr(w3_exc)[:120])

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

        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="approved",
            idempotency_key=idem_key,
        )
        t_chunks = time.perf_counter()
        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="sending",
            idempotency_key=idem_key,
        )
        force_dry = os.getenv("PUBLISH_FORCE_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}
        if force_dry:
            from publisher.publish_formatting import build_channel_message_html

            preview_html = build_channel_message_html(content, sources, draft_id=draft_id)
            log_event(
                logger,
                "publish.force_dry_run",
                draft_id=draft_id,
                html_preview=preview_html[:500],
                gate_ok=True,
            )
            return AdminPublishDraftResult(
                PublishFlowOutcome.DRY_RUN,
                draft_content=content,
                draft_sources=sources,
            )
        w5_mon: object | None = None
        try:
            from app.identity.insight_layer import score_insight_depth
            from app.identity.style_guide import detect_vertical, score_style_alignment
            from app.monetization.pipeline import enrich_with_monetization

            w5_vertical = "general"
            w5_signal = 0.55
            try:
                ex_m = json.loads(extras_json or "{}")
                w5_vertical = str(ex_m.get("category") or w5_vertical)
            except (json.JSONDecodeError, TypeError):
                pass
            w5_tz = getattr(settings, "newsroom_timezone", None) or "Europe/Moscow"
            w5_style = score_style_alignment(content, vertical=w5_vertical)
            w5_insight = score_insight_depth(content)
            w5_mon = await enrich_with_monetization(
                content,
                vertical=w5_vertical,
                insight_score=w5_insight,
                style_score=w5_style.score,
                signal_score=w5_signal,
                runtime_dir=settings.runtime_state_dir,
                newsroom_tz=w5_tz,
            )
            content = w5_mon.content
        except Exception as w5_enrich_exc:
            log_event(logger, "publish.w5_enrich_skipped", draft_id=draft_id, error=repr(w5_enrich_exc)[:120])

        try:
            first_id = await publish_draft_to_channel(
                bot,
                settings,
                draft_id=draft_id,
                content=content,
                sources=sources,
                draft_extras_json=extras_json,
                publish_attempt=publish_attempt,
                bypass_rate_limit=bypass_cadence,
            )
        except BaseException as exc:
            logger.exception("Failed to publish draft %s: %s", draft_id, exc)
            append_journal(
                settings.runtime_state_dir,
                tx_id=tx_id,
                draft_id=draft_id,
                state="failed",
                idempotency_key=idem_key,
                error=repr(exc),
            )
            log_event(logger, "publish.channel_send_failed", draft_id=draft_id, error=repr(exc))
            log_event(logger, "publish.failed", draft_id=draft_id, reason="telegram_send", error=repr(exc)[:500])
            log_publish_trace(
                event="failed",
                draft_id=draft_id,
                publish_attempt=publish_attempt,
                idempotency_key=idem_key,
                tx_id=tx_id,
                channel_id=getattr(settings, "channel_id", None),
                latency_ms=trace_timer.latency_ms,
                outcome="telegram_send",
                error=repr(exc),
            )
            async with session_scope() as session:
                await mark_draft_failed(session, draft_id, reason=repr(exc))
            try:
                from utils.operational_context import get_operational_log_fields
                from app.reliability.failed_draft_recovery import record_publish_failure

                await record_publish_failure(
                    draft_id,
                    reason=repr(exc),
                    correlation_id=str(get_operational_log_fields().get("correlation_id") or ""),
                )
            except Exception:
                pass
            return AdminPublishDraftResult(PublishFlowOutcome.SEND_FAILED, error=repr(exc))

        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="sent",
            idempotency_key=idem_key,
            channel_message_id=int(first_id),
        )

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
                append_journal(
                    settings.runtime_state_dir,
                    tx_id=tx_id,
                    draft_id=draft_id,
                    state="failed",
                    idempotency_key=idem_key,
                    error="finalize_state_mismatch",
                    channel_message_id=int(first_id),
                )
                log_event(logger, "publish.finalize_state_mismatch", draft_id=draft_id)
                return AdminPublishDraftResult(
                    PublishFlowOutcome.FINALIZE_MISMATCH,
                    draft_content=content,
                    draft_sources=sources,
                    channel_message_id=first_id,
                )

        append_journal(
            settings.runtime_state_dir,
            tx_id=tx_id,
            draft_id=draft_id,
            state="finalized",
            idempotency_key=idem_key,
            channel_message_id=int(first_id),
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
        try:
            from app.observability.runtime_health import record_publish_latency_ms

            record_publish_latency_ms(publish_total * 1000.0)
        except Exception:
            pass
        check_publish_trend(logger, settings, publish_total)

        inc("publishes")
        try:
            from app.ops.ledger.writer import record_published

            pub_item: dict[str, object] = {
                "news_id": f"draft:{draft_id}",
                "channel_name": "",
                "message_id": 0,
            }
            try:
                src_parsed = json.loads(sources or "[]")
                if isinstance(src_parsed, list) and src_parsed:
                    s0 = src_parsed[0]
                    if isinstance(s0, dict):
                        pub_item["channel_name"] = s0.get("channel") or ""
                        pub_item["message_id"] = int(s0.get("message_id") or 0)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            record_published(
                pub_item,
                channel_message_id=int(first_id),
                lane="scheduler",
                draft_id=draft_id,
            )
        except Exception as exc:
            logger.warning("ledger publish record skipped: %s", exc)
        log_event(
            logger,
            "publish.success",
            draft_id=draft_id,
            channel_message_id=first_id,
        )
        try:
            from app.analytics.telegram_stats import enqueue_post_for_tracking
            from app.growth.cadence_engine import record_growth_cadence_publish
            from editorial.cadence import topic_dedupe_key, record_publish

            primary_source = ""
            topic_bucket = "general"
            narrative_id = ""
            try:
                src_parsed = json.loads(sources or "[]")
                if isinstance(src_parsed, list) and src_parsed:
                    s0 = src_parsed[0]
                    if isinstance(s0, dict):
                        primary_source = str(s0.get("channel") or "")
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                ex = json.loads(extras_json or "{}")
                if isinstance(ex, dict):
                    topic_bucket = str(
                        ex.get("category")
                        or (ex.get("editorial_tags") or {}).get("category")
                        or topic_bucket
                    )
                    narrative_id = str((ex.get("narrative_intelligence") or {}).get("narrative_id") or "")
            except (json.JSONDecodeError, TypeError):
                pass
            tz = getattr(settings, "newsroom_timezone", None) or "Europe/Moscow"
            hour_local = 0
            try:
                from zoneinfo import ZoneInfo

                hour_local = datetime.now(ZoneInfo(tz)).hour
            except Exception:
                pass
            tk = topic_dedupe_key(topic_bucket)
            await enqueue_post_for_tracking(
                draft_id=int(draft_id),
                telegram_post_id=int(first_id),
                channel_id=int(getattr(settings, "channel_id", 0) or 0),
                primary_source=primary_source,
                topic_bucket=topic_bucket,
                publish_hour_local=hour_local,
            )
            record_publish(settings.runtime_state_dir, topic_key=tk)
            record_growth_cadence_publish(
                runtime_dir=settings.runtime_state_dir,
                topic_key=tk,
                content=content,
                topic_bucket=topic_bucket,
                narrative_id=narrative_id,
                newsroom_tz=tz,
            )
            try:
                from app.growth.narrative_tracker import record_narrative_publish

                if narrative_id:
                    await record_narrative_publish(narrative_id)
            except Exception:
                pass
            try:
                from app.growth.performance_memory import record_performance_memory

                await record_performance_memory(
                    draft_id=int(draft_id),
                    content=content,
                    topic_bucket=topic_bucket,
                    publish_hour_local=hour_local,
                    engagement_score=0.0,
                    virality_score=0.0,
                )
            except Exception:
                pass
            try:
                from app.flywheel.cross_post_orchestrator import (
                    execute_digest_mirror,
                    log_distribution_event,
                    plan_cross_post,
                    record_cross_post,
                )
                from app.flywheel.distribution_router import route_distribution_surface
                from app.flywheel.memory_compression import record_style_memory
                from app.flywheel.pipeline import content_hash
                from app.flywheel.retention_habit import active_habit_slot, record_habit_touch
                from app.identity.differentiation import record_published_structure
                from app.identity.insight_layer import score_insight_depth
                from app.identity.style_guide import detect_vertical, score_style_alignment
                from publisher.publish_formatting import build_channel_message_html

                vertical = detect_vertical(content, topic_bucket)
                style_v = score_style_alignment(content, vertical=vertical)
                insight_v = score_insight_depth(content)
                ch = content_hash(content)
                brk_flag = False
                w3_signal = 0.55
                try:
                    ex_w3 = json.loads(extras_json or "{}")
                    brk_flag = bool((ex_w3.get("breaking") or {}).get("is_breaking"))
                    pub_intel = ex_w3.get("publication_intel") or {}
                    if isinstance(pub_intel, dict):
                        pri = pub_intel.get("publication_priority") or {}
                        if isinstance(pri, dict):
                            raw_pri = float(pri.get("score") or w3_signal)
                            w3_signal = raw_pri / 100.0 if raw_pri > 1 else raw_pri
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

                route = route_distribution_surface(
                    settings,
                    is_breaking=brk_flag,
                    insight_score=insight_v,
                    style_score=style_v.score,
                    signal_score=w3_signal,
                )
                plan = plan_cross_post(
                    settings,
                    route,
                    runtime_dir=settings.runtime_state_dir,
                    content_hash=ch,
                )
                digest_mid: int | None = None
                if plan.mirror_digest and plan.digest_channel_id and not plan.skip:
                    html = build_channel_message_html(content, sources, draft_id=draft_id)
                    digest_mid = await execute_digest_mirror(
                        bot,
                        digest_channel_id=int(plan.digest_channel_id),
                        html=html,
                    )
                if not plan.skip:
                    record_cross_post(settings.runtime_state_dir, ch)
                    record_published_structure(content, runtime_dir=settings.runtime_state_dir)
                    headline_pattern = (content.split("\n", 1)[0] or "")[:48]
                    await record_style_memory(
                        vertical=vertical,
                        headline_pattern=headline_pattern,
                        style_score=style_v.score,
                        insight_score=insight_v,
                    )
                    await log_distribution_event(
                        draft_id=int(draft_id),
                        decision=route,
                        content_hash=ch,
                        mirrored_digest=digest_mid is not None,
                    )
                    slot = active_habit_slot(tz)
                    if slot:
                        record_habit_touch(settings.runtime_state_dir, slot.key)
                    log_event(
                        logger,
                        "publish.w3_flywheel_recorded",
                        draft_id=draft_id,
                        surface=route.surface.value,
                        digest_mirror=bool(digest_mid),
                    )
            except Exception as w3_post_exc:
                logger.warning("W3 post-publish hook skipped: %s", w3_post_exc)
            try:
                from datetime import UTC, datetime

                from app.monetization.financial_feedback import record_revenue_event
                from app.monetization.pipeline import record_monetized_publish
                from app.monetization.revenue_engine import route_revenue_stream, score_monetization_eligibility
                from db.models import PremiumContentLog

                elig = score_monetization_eligibility(
                    content,
                    vertical=vertical,
                    insight_score=insight_v,
                    style_score=style_v.score,
                    signal_score=w3_signal,
                )
                routing = route_revenue_stream(elig)
                est_amount = routing.estimated_cpm_usd / 1000.0
                await record_revenue_event(
                    draft_id=int(draft_id),
                    stream=routing.stream.value,
                    surface=route.surface.value,
                    amount_usd=est_amount,
                    topic_bucket=topic_bucket,
                    eligibility_score=elig.score,
                    extras={"reason": routing.eligibility.reason},
                )
                sponsor_flag = bool(getattr(w5_mon, "sponsor_injected", False)) if w5_mon else False
                premium_flag = bool(getattr(w5_mon, "is_premium", False)) if w5_mon else False
                record_monetized_publish(
                    settings.runtime_state_dir,
                    sponsor_injected=sponsor_flag,
                    is_premium=premium_flag,
                )
                if premium_flag and getattr(w5_mon, "premium_body", ""):
                    prem_ch_raw = __import__("os").getenv("TELEGRAM_PREMIUM_CHANNEL_ID", "").strip()
                    if prem_ch_raw:
                        from app.flywheel.cross_post_orchestrator import execute_digest_mirror
                        from publisher.publish_formatting import build_channel_message_html

                        prem_html = build_channel_message_html(
                            str(w5_mon.premium_body),
                            sources,
                            draft_id=draft_id,
                        )
                        await execute_digest_mirror(
                            bot,
                            digest_channel_id=int(prem_ch_raw),
                            html=prem_html,
                        )
                    try:
                        from app.monetization.premium_layer import content_hash as prem_hash

                        async with session_scope() as session:
                            session.add(
                                PremiumContentLog(
                                    draft_id=int(draft_id),
                                    tier="premium",
                                    insight_score=insight_v,
                                    free_preview_hash=prem_hash(content)[:24],
                                    premium_channel_id=int(prem_ch_raw) if prem_ch_raw else None,
                                    published_at=datetime.now(UTC),
                                    created_at=datetime.now(UTC),
                                )
                            )
                    except Exception:
                        pass
                log_event(
                    logger,
                    "publish.w5_revenue_recorded",
                    draft_id=draft_id,
                    stream=routing.stream.value,
                    amount_usd=round(est_amount, 6),
                )
            except Exception as w5_post_exc:
                logger.warning("W5 post-publish hook skipped: %s", w5_post_exc)
        except Exception as exc:
            logger.warning("analytics/cadence post-publish hook skipped: %s", exc)
        try:
            from app.observability.execution_graph_trace import record_publish_success

            record_publish_success(draft_id=draft_id)
        except Exception:
            pass
        try:
            from app.observability.prepublic_qa import (
                mirror_publish_to_qa_chat,
                prepublic_qa_enabled,
                record_publish_decision_explanation,
            )

            if prepublic_qa_enabled():
                await mirror_publish_to_qa_chat(
                    bot,
                    settings,
                    draft_id=draft_id,
                    content_preview=content[:500],
                    channel_message_id=int(first_id),
                )
                record_publish_decision_explanation(
                    settings.runtime_state_dir,
                    draft_id=draft_id,
                    decision="published",
                    detail={"channel_message_id": int(first_id)},
                )
        except Exception:
            pass
        try:
            import sqlite3

            from utils.database_url import sqlite_path_from_url

            from app.observability.publish_audit import log_publish_audit, lookup_source_tick_id

            db_path = sqlite_path_from_url(settings.database_url)
            tick_id = ""
            if db_path:
                conn = sqlite3.connect(db_path, timeout=3.0)
                tick_id = lookup_source_tick_id(conn, draft_id)
                conn.close()
            log_publish_audit(
                draft_id=draft_id,
                publish_decision="published",
                publish_mode=publish_mode,
                publish_source_tick_id=tick_id,
                extra={"channel_message_id": int(first_id)},
            )
        except Exception:
            pass
        try:
            from app.runtime_activity import record_publish_success as record_runtime_publish

            record_runtime_publish()
        except Exception:
            pass
        try:
            from app.editorial.feedback_loop import record_publish_success

            trust_score = None
            signal_score = None
            manual = False
            if extras_json:
                ex = json.loads(extras_json)
                if isinstance(ex, dict):
                    np = ex.get("newsroom_product")
                    if isinstance(np, dict):
                        manual = bool(np.get("manual_review_required"))
                        pol = np.get("publish_policy")
                        if isinstance(pol, dict):
                            trust_score = pol.get("trust_score")
                            signal_score = pol.get("signal_score")
            record_publish_success(
                draft_id=draft_id,
                runtime_dir=getattr(settings, "runtime_state_dir", None),
                signal_score=float(signal_score) if signal_score is not None else None,
                trust_score=float(trust_score) if trust_score is not None else None,
                manual_review=manual,
            )
        except Exception:
            pass
        log_event(
            logger,
            "publish.succeeded",
            draft_id=draft_id,
            channel_message_id=first_id,
            idempotency_key=idem_key,
        )
        log_publish_trace(
            event="success",
            draft_id=draft_id,
            publish_attempt=publish_attempt,
            idempotency_key=idem_key,
            tx_id=tx_id,
            channel_id=getattr(settings, "channel_id", None),
            telegram_message_id=int(first_id),
            latency_ms=trace_timer.latency_ms,
            outcome="ok",
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
        try:
            from app.editorial.cadence_intelligence import record_cadence_intelligence
            from app.editorial.staging_mode import is_final_staging_mode, record_staging_publish

            record_cadence_intelligence(
                settings.runtime_state_dir,
                content=content,
                topic_key=topic_dedupe_key(th),
            )
            if is_final_staging_mode(settings):
                record_staging_publish(settings.runtime_state_dir)
        except Exception:
            pass

        await _idem_record_success(settings, idem_key, draft_id, first_id)
        mark_idempotency_processed(
            settings.runtime_state_dir,
            idem_key,
            draft_id=draft_id,
            channel_message_id=int(first_id),
        )
        try:
            from ops.pipeline.ingestion_ledger import IngestionLedger
            from ops.pipeline.state_machine import NewsState

            IngestionLedger(settings.runtime_state_dir).append(
                news_id=idem_key[:32],
                from_state=NewsState.APPROVED,
                to_state=NewsState.PUBLISHED,
                decision_reason="publish_ok",
                idempotency_key=idem_key,
                extra={"draft_id": draft_id, "channel_message_id": int(first_id)},
            )
        except Exception:
            pass

        return AdminPublishDraftResult(
            PublishFlowOutcome.OK,
            draft_content=content,
            draft_sources=sources,
            channel_message_id=first_id,
        )
