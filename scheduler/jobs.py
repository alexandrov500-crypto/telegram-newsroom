from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import timedelta

from aiogram import Bot
from openai import AsyncOpenAI

from ai.editorial import compose_post_with_headline
from ai.preprocess import truncate_raw_posts_for_openai
from ai.quality_score import compute_quality_scores
from ai.summary_quality import observe_draft_quality
from app.config import Settings
from editorial.cadence import evaluate_publish_gate, topic_dedupe_key
from editorial.cluster_rank import evaluate_cluster_for_pipeline
from editorial.confidence import compute_editorial_confidence
from editorial.entities import extract_entities, record_entity_cooccurrence
from editorial.events import (
    append_event_history,
    build_event_cluster,
    build_event_identity,
    classify_event_evolution,
    compute_event_fingerprint,
    load_event_history,
)
from editorial.feedback import collect_editorial_feedback_stats
from editorial.headline_quality import evaluate_headline_quality
from editorial.policy import dominant_channel_key, load_editorial_policy_bundle, resolve_effective_policy
from editorial.publication_priority import compute_publication_priority_score, compute_publish_readiness_score
from editorial.scoring import compute_editorial_score_card
from editorial.trends import detect_topic_trends, source_convergence_score
from bot.admin_handlers import notify_admin_new_draft
from collector.service import collect_all_channels
from dashboard.timeline import append_timeline_event
from collector.telethon_client import build_telethon_client
from db.models import RawPost
from db.repository import (
    create_draft_and_mark_posts_processed,
    draft_duplicate_intel,
    draft_should_be_skipped_as_duplicate,
    fetch_recent_drafts_for_dedupe,
    fetch_recent_published_for_dedupe,
    fetch_unprocessed_raw_posts,
    get_draft_by_id,
    mark_raw_posts_processed,
    merge_draft_extras,
    list_due_scheduled_draft_ids,
    utcnow,
)
from db.retention import delete_old_processed_raw_posts, delete_old_rejected_drafts
from db.session import session_scope
from scheduler.pipeline_lock import get_pipeline_lock
from scheduler.precluster import avg_pairwise_lexical_cohesion, select_cluster_for_summarization
from scheduler.runtime_context import PipelineContext, set_pipeline_context
from utils.diagnostics import db_file_size_bytes, log_runtime_diagnostics, rss_bytes_best_effort
from utils.error_classifier import classify_runtime_error
from utils.metrics import (
    inc,
    log_pipeline_metrics,
    observe_histogram,
    record_pipeline_duration,
)
from utils.observability import (
    check_phase_trends_after_tick,
    check_tick_anomalies,
    configure_deque_maxlen,
    log_operational_summary,
    log_retention_db_effect,
    record_collect_duration,
    record_duplicate_skip,
    record_openai_duration,
    record_pipeline_wall_sample,
    reset_duplicate_skip_streak,
)
from utils.operational_context import (
    begin_pipeline_tick,
    correlation_fields_for_draft,
    reset_correlation_id,
    reset_tick_id,
)
from utils.runtime_events import append_runtime_event
from utils.runtime_state_store import maybe_flush_runtime_events_to_snapshot, try_save_runtime_snapshot
from utils.sqlite_maintenance import maybe_run_sqlite_maintenance
from utils.structured_log import log_event
from utils.source_reputation import export_channel_scores_for_priority
from utils.text_hash import sha256_hex

logger = logging.getLogger(__name__)


def build_pipeline_context(
    settings: Settings,
    bot: Bot,
    openai: AsyncOpenAI,
    *,
    ai_pipeline_enabled: bool = True,
    collector_enabled: bool = True,
) -> PipelineContext:
    configure_deque_maxlen(settings)
    ctx = PipelineContext(
        settings=settings,
        bot=bot,
        openai=openai,
        ai_pipeline_enabled=ai_pipeline_enabled,
        collector_enabled=collector_enabled,
    )
    set_pipeline_context(ctx)
    return ctx


def _round_timings(d: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 4) for k, v in d.items()}


def _log_pipeline_idle(stage: str, reason: str, **extra: object) -> None:
    """Explicit INFO when a tick step exits without downstream work (go-live visibility)."""
    logger.info("pipeline idle at %s: %s", stage, reason)
    log_event(logger, "pipeline.idle", stage=stage, reason=reason, **extra)


async def _collect_step(ctx: PipelineContext) -> None:
    from app.dependency_state import get_dependency_state
    from app.ops.control_plane.guards import ingestion_allowed, log_guard_skip
    from app.ops.ledger.replay import replay_mode_enabled, run_replay_collect_step
    from app.telethon_bootstrap import telethon_session_configured

    if replay_mode_enabled():
        n = await run_replay_collect_step(ctx)
        ctx.tick_collect_rows = 0
        log_event(logger, "collector.replay_mode", replayed=n)
        logger.info("collector: REPLAY_MODE replayed=%s events (no Telegram)", n)
        return

    if not ingestion_allowed():
        log_guard_skip("collector", "ingestion_disabled_or_halt")
        log_event(logger, "collector.skipped", reason="ops_ingestion_paused")
        return

    deps = get_dependency_state()
    if telethon_session_configured(ctx.settings) and deps.collector_enabled:
        ctx.collector_enabled = True
    elif not ctx.collector_enabled and telethon_session_configured(ctx.settings):
        logger.info("collector re-enabled: telethon session present (startup flag was degraded)")
        ctx.collector_enabled = True

    if not ctx.collector_enabled:
        log_event(logger, "collector.skipped", reason="telethon_degraded")
        logger.warning("collector skipped: telethon_degraded (no ingest this tick)")
        return
    logger.info("collector running")
    import asyncio

    from app.runtime.collect_cycle_guard import (
        begin_collect,
        collect_timeout_sec,
        end_collect,
    )
    from app.runtime_lifecycle import emit_lifecycle, lifecycle_span_ms
    from collector.telethon_connect import connect_telethon_resilient, disconnect_telethon_safe
    from utils.operational_context import current_tick_id

    settings = ctx.settings
    inserted_total = 0
    collect_ok = False
    collect_err = ""
    from collector.progress import CollectProgress

    collect_progress = CollectProgress()
    t0 = time.perf_counter()
    begin_collect(tick_id=current_tick_id() or "")
    emit_lifecycle("collector.batch.started", channel_count=len(settings.source_channels))
    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )

    async def _collect_body() -> None:
        nonlocal inserted_total, collect_ok, collect_err
        if not await connect_telethon_resilient(client, label="pipeline_collect"):
            collect_err = "telethon_connect_timeout"
            from app.runtime_activity import record_collect_failure

            record_collect_failure(reason=collect_err)
            log_event(logger, "collector.connect_failed", reason=collect_err)
            _log_pipeline_idle("collector", collect_err)
            return
        if not await client.is_user_authorized():
            collect_err = "telethon_unauthorized"
            log_event(logger, "collector.telethon_unauthorized")
            _log_pipeline_idle("collector", collect_err)
            return
        channel_list = list(settings.source_channels)
        try:
            from app.sources.registry import ensure_registry_maintenance, load_active_source_handles

            await ensure_registry_maintenance()
            channel_list = await load_active_source_handles(settings)
        except Exception:
            pass
        collect_progress.planned_total = len(channel_list)
        use_sharded = __import__("os").getenv("COLLECT_PARALLEL_ENABLED", "true").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        async with session_scope() as session:
            if use_sharded:
                from collector.sharded_collect import collect_channels_sharded

                inserted_total = await collect_channels_sharded(
                    client,
                    session,
                    channels=channel_list,
                    limit_per_channel=settings.collect_messages_per_channel,
                    telethon_max_attempts=settings.telethon_op_max_attempts,
                    channel_delay_seconds=settings.channel_collect_delay_seconds,
                    progress=collect_progress,
                )
            else:
                from collector.service import collect_all_channels

                inserted_total = await collect_all_channels(
                    client,
                    session,
                    channels=channel_list,
                    limit_per_channel=settings.collect_messages_per_channel,
                    telethon_max_attempts=settings.telethon_op_max_attempts,
                    channel_delay_seconds=settings.channel_collect_delay_seconds,
                    progress=collect_progress,
                )
        inc("posts_collected", inserted_total)
        if inserted_total > 0:
            from app.runtime_activity import record_collect_success

            record_collect_success(new_rows=inserted_total)
        ctx.tick_collect_rows = inserted_total
        collect_ok = True
        log_event(
            logger,
            "collector.pipeline_inserted_total",
            new_rows=inserted_total,
            channel_count=len(settings.source_channels),
        )
        logger.info(
            "collector finished: new_rows=%s channels=%s",
            inserted_total,
            len(settings.source_channels),
        )
        from app.pipeline_debug import pipeline_debug_active
        from scheduler.pipeline_trace import log_pipeline_trace

        if pipeline_debug_active(settings):
            log_pipeline_trace(
                logger,
                stage="collector",
                decision="proceed" if inserted_total >= 0 else "suppress",
                reason=f"inserted_total={inserted_total}",
            )

    try:
        cap = collect_timeout_sec()
        if cap > 0:
            await asyncio.wait_for(_collect_body(), timeout=cap)
        else:
            await _collect_body()
    except asyncio.TimeoutError:
        cap = collect_timeout_sec()
        collect_err = f"collect_cycle_timeout:{cap}s"
        inserted_total = collect_progress.new_rows_total
        skipped = collect_progress.channels_skipped_count()
        log_event(
            logger,
            "collector.channels_skipped",
            count=skipped,
            planned=collect_progress.planned_total,
            processed=collect_progress.channels_processed,
        )
        if inserted_total > 0:
            from app.runtime_activity import record_collect_success

            record_collect_success(new_rows=inserted_total)
            log_event(
                logger,
                "collector.timeout_preserved",
                new_rows=inserted_total,
                channels_processed=collect_progress.channels_processed,
                channels_skipped=skipped,
                timeout_sec=cap,
                tick_id=current_tick_id(),
            )
        from app.runtime_activity import record_collect_failure

        record_collect_failure(reason=collect_err)
        log_event(logger, "COLLECT_CYCLE_TIMEOUT", timeout_sec=cap, tick_id=current_tick_id())
        _log_pipeline_idle("collector", collect_err)
    except Exception as exc:
        collect_err = repr(exc)[:300]
        from app.runtime_activity import record_collect_failure

        record_collect_failure(reason=collect_err)
        logger.exception("Collection failed: %s", exc)
        log_event(logger, "collector.pipeline_failed", error=collect_err)
    finally:
        await disconnect_telethon_safe(client, label="pipeline_collect")
        end_collect(success=collect_ok, error=collect_err)
        ctx.tick_timings["collect_sec"] = time.perf_counter() - t0
        observe_histogram("collect_duration_seconds", ctx.tick_timings["collect_sec"])
        emit_lifecycle(
            "collector.batch.completed",
            new_rows=inserted_total,
            event_duration_ms=lifecycle_span_ms(t0),
        )


async def _retention_step(settings: Settings) -> tuple[float, int, int]:
    t0 = time.perf_counter()
    if settings.retention_processed_raw_days <= 0 and settings.retention_rejected_draft_days <= 0:
        return time.perf_counter() - t0, 0, 0
    now = utcnow()
    deleted_raw = 0
    deleted_drafts = 0
    try:
        async with session_scope() as session:
            if settings.retention_processed_raw_days > 0:
                cutoff_raw = now - timedelta(days=settings.retention_processed_raw_days)
                deleted_raw = await delete_old_processed_raw_posts(session, older_than=cutoff_raw)
            if settings.retention_rejected_draft_days > 0:
                cutoff_drafts = now - timedelta(days=settings.retention_rejected_draft_days)
                deleted_drafts = await delete_old_rejected_drafts(session, older_than=cutoff_drafts)
        if deleted_raw or deleted_drafts:
            log_event(
                logger,
                "retention.cleanup",
                deleted_processed_raw_posts=deleted_raw,
                deleted_rejected_drafts=deleted_drafts,
            )
    except Exception as exc:
        logger.exception("Retention cleanup failed: %s", exc)
        log_event(logger, "retention.cleanup_failed", error=repr(exc))
    return time.perf_counter() - t0, deleted_raw, deleted_drafts


async def _summarize_step(ctx: PipelineContext) -> None:
    from app.state.pipeline_execution_wrapper import execute_pipeline_step

    await execute_pipeline_step(ctx, "summarize", lambda: _summarize_step_impl(ctx))


async def _summarize_step_impl(ctx: PipelineContext) -> None:
    from app.state.pipeline_execution_wrapper import require_pipeline_wrapper_active

    require_pipeline_wrapper_active("summarize_step")
    from app.openai_circuit import get_openai_circuit
    from app.pipeline_debug import (
        ai_gating_snapshot,
        debug_bypass_suppressions,
        pipeline_debug_active,
    )
    from ops.economics.budgets import allow_ai_request
    from ops.economics.economic_mode import load_economic_mode
    from ops.economics.load_shedding import should_skip_summarize_for_pressure
    from scheduler.pipeline_trace import log_pipeline_trace

    settings = ctx.settings
    rd = settings.runtime_state_dir
    from app.recovery.pipeline_overrides import (
        effective_ai_gate_open,
        is_minimal_pipeline_mode,
        log_upstream_pipeline_state,
        recovery_bypass_active,
    )
    from app.state.pipeline_decision_engine import PipelineNextAction

    pd = ctx.pipeline_decision
    if pd is None:
        from app.state.pipeline_decision_engine import make_pipeline_decision
        from app.recovery.pipeline_context_builder import build_pipeline_decision_context

        pd = make_pipeline_decision(build_pipeline_decision_context())

    log_event(logger, "summarize_entry", stage="summarize_step_impl")

    debug = pipeline_debug_active(settings)
    bypass = debug_bypass_suppressions(settings) or recovery_bypass_active()
    if is_minimal_pipeline_mode():
        bypass = True
    if debug:
        log_event(logger, "pipeline.debug_mode_active", ai_gating=ai_gating_snapshot(ctx=ctx))

    econ = load_economic_mode(rd).value
    shed_skip, shed_reason = should_skip_summarize_for_pressure(
        settings, rd, priority_level="high" if debug else "medium"
    )
    backlog_decision = pd.observability_trace.get("backlog_size", 0) or 0
    if shed_skip and not bypass:
        if pd.should_execute and int(backlog_decision) > 0:
            log_event(
                logger,
                "summarize_skip_reason",
                reason=f"load_shedding_overridden_by_decision_engine:{shed_reason}",
                stage="load_shedding",
            )
            bypass = True
        else:
            log_event(logger, "scheduler.summarize_skipped", reason=shed_reason, stage="load_shedding")
            ctx.tick_summarize_idle_reason = f"load_shedding:{shed_reason}"
            log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
            _log_pipeline_idle("summarize", ctx.tick_summarize_idle_reason)
            log_pipeline_trace(logger, stage="scoring", decision="suppress", reason=shed_reason)
            return
    ai_ok, ai_reason = allow_ai_request(rd, priority_level="high" if debug else "medium", economic_mode=econ)
    if not ai_ok and not bypass:
        if pd.should_execute and int(backlog_decision) > 0:
            log_event(
                logger,
                "summarize_skip_reason",
                reason=f"ai_budget_overridden_by_decision_engine:{ai_reason}",
                stage="ai_budget",
            )
            bypass = True
        else:
            log_event(logger, "scheduler.summarize_skipped", reason=ai_reason, stage="ai_budget")
            ctx.tick_summarize_idle_reason = f"ai_budget:{ai_reason}"
            log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
            _log_pipeline_idle("summarize", ctx.tick_summarize_idle_reason)
            log_pipeline_trace(logger, stage="scoring", decision="suppress", reason=ai_reason)
            return

    circuit = get_openai_circuit()
    circuit_allows = circuit.allow_request()
    exec_dec = ctx.pipeline_execution
    if exec_dec is not None:
        ai_gate_open = exec_dec.ai_gate_open
    else:
        ai_gate_open = effective_ai_gate_open(ctx_ai_enabled=ctx.ai_pipeline_enabled, circuit=circuit)
    log_upstream_pipeline_state(
        ctx_ai_enabled=pd.should_execute,
        circuit_allows=circuit_allows,
        ai_gate_open=ai_gate_open,
    )
    log_event(
        logger,
        "summarize_execution_path",
        ai_gate_open=ai_gate_open,
        use_fallback=exec_dec.use_fallback if exec_dec else not ai_gate_open,
        mode=exec_dec.mode.value if exec_dec else "unknown",
    )
    if not ai_gate_open and not bypass:
        log_event(
            logger,
            "scheduler.summarize_fallback",
            reason="openai_degraded",
            stage="startup",
            circuit_state=circuit.state().value,
            recovery="rule_fallback",
        )
    openai = ctx.openai
    settings = ctx.settings
    bot = ctx.bot

    t_db = time.perf_counter()
    async with session_scope() as session:
        posts = await fetch_unprocessed_raw_posts(session, limit=settings.raw_fetch_cap)
        try:
            feedback_stats = await collect_editorial_feedback_stats(session)
        except Exception:
            feedback_stats = None
    ctx.tick_timings["db_fetch_unprocessed_sec"] = time.perf_counter() - t_db

    if not posts:
        from app.editorial.stability.synthesis_flow import try_create_stability_draft

        if await try_create_stability_draft(ctx, trigger="no_posts"):
            log_event(logger, "stability.fill_no_posts", outcome="draft_created", draft_id=ctx.tick_draft_id)
            ctx.last_cluster_size = 0
            return
        log_event(logger, "scheduler.summarize_skipped", reason="no_unprocessed_posts", stage="fetch_posts")
        ctx.tick_summarize_idle_reason = "no_unprocessed_posts"
        _log_pipeline_idle("summarize", ctx.tick_summarize_idle_reason)
        log_pipeline_trace(logger, stage="clustering", decision="suppress", reason="no_unprocessed_posts")
        ctx.last_cluster_size = 0
        return

    t_cl = time.perf_counter()
    cluster = select_cluster_for_summarization(
        posts,
        bucket_hours=settings.precluster_bucket_hours,
        max_posts=settings.max_cluster_posts,
        min_posts_fallback=settings.min_raw_posts_for_ai,
        min_lexical_jaccard=settings.cluster_min_lexical_jaccard,
        min_lexical_jaccard_with_last=settings.cluster_min_pair_last_jaccard,
        trim_bucket_multiplier=settings.precluster_trim_bucket_multiplier,
    )
    if len(cluster) > 1:
        cohesion_val = avg_pairwise_lexical_cohesion(cluster)
        min_cohesion = max(0.02, float(settings.cluster_min_lexical_jaccard))
        if cohesion_val < min_cohesion:
            log_event(
                logger,
                "scheduler.cluster_low_cohesion",
                cluster_size=len(cluster),
                cohesion=round(cohesion_val, 4),
                min_cohesion=min_cohesion,
                kept="newest",
            )
            cluster = [cluster[-1]]
    ctx.last_cluster_size = len(cluster)
    # One Telegram post = one story; do not require N posts in a cluster to draft.
    min_posts_required = 1

    if len(cluster) < min_posts_required:
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason="cluster_below_min_posts",
            cluster_size=len(cluster),
            min_required=min_posts_required,
            stage="precluster",
        )
        log_pipeline_trace(
            logger,
            stage="clustering",
            decision="suppress",
            reason="cluster_below_min_posts",
            extra={"cluster_size": len(cluster)},
        )
        ctx.tick_summarize_idle_reason = f"cluster_below_min_posts:{len(cluster)}"
        _log_pipeline_idle("clustering", ctx.tick_summarize_idle_reason)
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return

    logger.info("cluster created: size=%s fingerprint_pending=true", len(cluster))
    combined_text = "\n".join((p.text or "")[:2000] for p in cluster)
    fp = compute_event_fingerprint(cluster)
    desk = None
    escore = None
    try:
        from app.editorial.desk_filter import evaluate_desk_filter, persist_rejection
        from app.editorial.scoring_engine import persist_score, score_story
        from app.pipeline.breaking_lane import BreakingItem, enqueue_breaking
        from ops.pipeline.ingestion_ledger import IngestionLedger
        from ops.pipeline.observability import emit_ops_event
        from ops.pipeline.state_machine import NewsState

        chans = list({str(p.channel_name or "") for p in cluster})
        escore = score_story(text=combined_text, sources=chans, runtime_dir=settings.runtime_state_dir)
        persist_score(settings.runtime_state_dir, article_id=fp, score=escore, sources=chans)
        desk = evaluate_desk_filter(
            combined_text,
            escore,
            sources=chans,
            runtime_dir=settings.runtime_state_dir,
            bypass=bypass,
        )
        led = IngestionLedger(settings.runtime_state_dir)
        led.append(
            news_id=fp[:32],
            from_state=NewsState.VALIDATED,
            to_state=NewsState.CLUSTERED,
            decision_reason=f"cluster_size={len(cluster)}",
            idempotency_key=fp,
        )
        led.append(
            news_id=fp[:32],
            from_state=NewsState.CLUSTERED,
            to_state=NewsState.SCORED,
            decision_reason=escore.reason,
            idempotency_key=fp,
            extra=escore.to_dict(),
        )
        emit_ops_event(
            "editorial_scored",
            runtime_dir=settings.runtime_state_dir,
            news_id=fp[:32],
            state=NewsState.SCORED.value,
            decision_reason=escore.reason,
            lane=escore.lane,
            final_priority_score=escore.final_priority_score,
        )
        if not desk.publish and not bypass:
            persist_rejection(
                settings.runtime_state_dir,
                article_id=fp,
                text_preview=combined_text,
                decision=desk,
                sources=chans,
                escore=escore,
            )
            led.append(
                news_id=fp[:32],
                from_state=NewsState.SCORED,
                to_state=NewsState.REJECTED,
                decision_reason=f"desk:{desk.reason}",
                idempotency_key=fp,
                extra=desk.to_dict(),
            )
            emit_ops_event(
                "desk_rejected",
                runtime_dir=settings.runtime_state_dir,
                news_id=fp[:32],
                state=NewsState.REJECTED.value,
                decision_reason=desk.reason,
                editorial_category=desk.editorial_category,
                quality_score=desk.quality_score,
            )
            log_pipeline_trace(
                logger,
                stage="desk_filter",
                cluster_id=fp,
                decision="reject",
                reason=desk.reason,
                extra=desk.to_dict(),
            )
            ctx.tick_summarize_idle_reason = f"desk_reject:{desk.reason}"
            _log_pipeline_idle("summarize", ctx.tick_summarize_idle_reason)
            logger.info(
                "desk filter rejected cluster: reason=%s category=%s quality=%.1f",
                desk.reason,
                desk.editorial_category,
                desk.quality_score,
            )
            from app.editorial.stability.synthesis_flow import try_create_stability_draft

            if await try_create_stability_draft(ctx, trigger="desk", exclude_fingerprint=fp):
                log_event(
                    logger,
                    "stability.fill_desk_reject",
                    outcome="draft_created",
                    draft_id=ctx.tick_draft_id,
                    desk_reason=desk.reason,
                )
                return
            post_ids = [int(p.id) for p in cluster if getattr(p, "id", None)]
            if post_ids:
                try:
                    async with session_scope() as session:
                        await mark_raw_posts_processed(session, post_ids, utcnow())
                except Exception as exc:
                    log_event(
                        logger,
                        "desk_reject_mark_processed_failed",
                        error=repr(exc)[:200],
                        post_count=len(post_ids),
                    )
            return
        led.append(
            news_id=fp[:32],
            from_state=NewsState.SCORED,
            to_state=NewsState.APPROVED,
            decision_reason=f"desk:{desk.reason}",
            idempotency_key=fp,
            extra=desk.to_dict(),
        )
        emit_ops_event(
            "desk_approved",
            runtime_dir=settings.runtime_state_dir,
            news_id=fp[:32],
            state=NewsState.APPROVED.value,
            decision_reason=desk.reason,
            editorial_category=desk.editorial_category,
            quality_score=desk.quality_score,
            priority_tier=desk.priority_tier,
        )
        logger.info(
            "desk filter approved: category=%s quality=%.1f tier=%s reason=%s",
            desk.editorial_category,
            desk.quality_score,
            desk.priority_tier,
            desk.reason,
        )
        if desk.breaking_override or desk.editorial_category == "breaking" or escore.is_breaking:
            ctx.is_breaking_stream = True
            enqueue_breaking(
                BreakingItem(
                    article_id=fp,
                    text=combined_text[:4000],
                    sources=chans,
                    breaking_score=max(escore.breaking_score, 0.75 if desk.breaking_override else 0.0),
                    priority_level=10 if desk.priority_tier == "priority" else 7,
                ),
                runtime_dir=settings.runtime_state_dir,
            )
    except Exception as exc:
        log_event(logger, "scheduler.editorial_scoring_failed", error=repr(exc)[:200])
    ctx.debug_trace_cluster_id = fp
    log_pipeline_trace(
        logger,
        stage="clustering",
        cluster_id=fp,
        decision="proceed",
        reason=f"cluster_size={len(cluster)}",
    )
    history = load_event_history(settings.runtime_state_dir)
    evo = classify_event_evolution(fp, combined_text=combined_text, history=history)
    identity = build_event_identity(cluster)
    ents = extract_entities(combined_text)
    record_entity_cooccurrence(settings.runtime_state_dir, ents)
    if desk is not None and desk.publish:
        try:
            from app.editorial.stability.elastic_fill import record_cluster_buffer

            record_cluster_buffer(
                settings.runtime_state_dir,
                fingerprint=fp,
                combined_text=combined_text,
                sources=chans,
                topic_hint=identity.topic_hint,
                editorial_category=str(desk.editorial_category or "macro"),
                quality_score=float(desk.quality_score or 0.0),
            )
        except Exception:
            pass

    channel_scores = export_channel_scores_for_priority(settings.runtime_state_dir)
    entity_norms = tuple(e.normalized for e in ents)
    from editorial.governance.diversity_controls import (
        apply_cooldowns,
        record_selection,
        record_suppression_metric,
    )
    from editorial.governance.explainability import build_draft_governance_metadata
    from editorial.governance.ledger import append_decision
    from editorial.governance.policies_engine import evaluate_policies, record_topic_selected
    from editorial.governance.ranking import rank_clusters, score_cluster_candidate
    from editorial.policy import dominant_channel_key
    from editorial.suppression_memory import record_suppression_ttl

    dom_ch = dominant_channel_key(cluster)
    ranking_trace = score_cluster_candidate(
        cluster,
        runtime_dir=settings.runtime_state_dir,
        fingerprint=fp,
        topic_hint=identity.topic_hint,
        evolution_kind=str(evo.kind),
        duplicate_similarity_pct=0.0,
        entity_norms=entity_norms,
    )
    ranked = rank_clusters(
        [
            {
                "posts": cluster,
                "fingerprint": fp,
                "topic_hint": identity.topic_hint,
                "evolution_kind": str(evo.kind),
                "entity_norms": entity_norms,
            }
        ],
        runtime_dir=settings.runtime_state_dir,
    )
    try:
        from ops.trust.canary import record_shadow_comparison

        record_shadow_comparison(settings.runtime_state_dir, live_ranked=ranked)
    except Exception:
        pass
    policy_matches, gov_suppress, gov_reason = evaluate_policies(
        cluster,
        runtime_dir=settings.runtime_state_dir,
        topic_key=identity.topic_hint,
        dominant_channel=dom_ch,
        fingerprint=fp,
    )
    starvation_recovery = False
    try:
        from app.editorial.desk_starvation import desk_threshold_context

        starvation_recovery = desk_threshold_context().publish_starvation_detected
    except Exception:
        pass
    from app.editorial.burnin_governance import (
        cluster_suppress_strict,
        governance_snapshot,
        source_cooldown_sec,
    )

    _gov_snap = governance_snapshot()
    _cooldown_sec = source_cooldown_sec()
    div_blocked, div_codes = apply_cooldowns(
        settings.runtime_state_dir,
        topic_key=identity.topic_hint,
        channels=[str(p.channel_name or "") for p in cluster],
        cooldown_sec=_cooldown_sec,
        source_cap=12 if _gov_snap.get("burnin_soft_governance") else 8,
        topic_cap=8 if _gov_snap.get("burnin_soft_governance") else 5,
    )
    _div_enforced = div_blocked and cluster_suppress_strict() and not starvation_recovery
    _publishing_mode = "core"
    from app.editorial.stability.controller import evaluate_stability_context
    from app.editorial.stability.mode_controller import (
        primary_governance_suppress_reason,
        should_bypass_governance,
    )

    _stab_ctx = evaluate_stability_context(
        newsroom_tz=settings.newsroom_timezone,
        cluster_size=len(cluster),
        governance_blocked=bool(
            ranking_trace.hard_block or (gov_suppress and not starvation_recovery) or _div_enforced
        ),
    )
    _gov_block = ranking_trace.hard_block or (gov_suppress and not starvation_recovery) or _div_enforced
    _stab_bypass = should_bypass_governance(
        _stab_ctx,
        div_blocked=div_blocked,
        gov_suppress=gov_suppress,
        hard_block=ranking_trace.hard_block,
    )
    _publishing_mode = _stab_ctx.mode.value if _stab_bypass else "core"
    if _gov_block and not bypass and not _stab_bypass:
        reasons = list(ranking_trace.reason_codes) + div_codes
        if gov_reason:
            reasons.append(gov_reason)
        _primary_suppress = primary_governance_suppress_reason(
            list(ranking_trace.reason_codes),
            div_codes,
            gov_reason=gov_reason,
        )
        append_decision(
            runtime_dir=settings.runtime_state_dir,
            decision_type="cluster_governance_suppress",
            outcome="suppressed",
            subject_id=fp,
            reason_codes=reasons[:24],
            ranking_trace=ranking_trace.to_dict(),
            policy_matches=policy_matches,
        )
        if not starvation_recovery:
            record_suppression_ttl(
                settings.runtime_state_dir,
                fp,
                1800.0,
                reason=gov_reason or _primary_suppress or "",
            )
        record_suppression_metric(settings.runtime_state_dir, gov_reason or "governance")
        inc("skipped_intelligence_suppress")
        log_event(
            logger,
            "scheduler.cluster_suppressed",
            reasons=reasons,
            stage="governance",
            primary_suppress=_primary_suppress,
            publishing_mode=_stab_ctx.mode.value,
        )
        log_pipeline_trace(
            logger,
            stage="scoring",
            cluster_id=fp,
            decision="suppress",
            reason="governance",
            policy_matches=[str(p) for p in policy_matches][:16],
        )
        ctx.tick_summarize_idle_reason = f"cluster_governance:{_primary_suppress[:120]}"
        from app.editorial.stability.synthesis_flow import try_create_stability_draft

        if await try_create_stability_draft(ctx, trigger="governance", exclude_fingerprint=fp):
            log_event(
                logger,
                "stability.fill_governance",
                outcome="draft_created",
                draft_id=ctx.tick_draft_id,
                primary_suppress=_primary_suppress,
            )
            ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
            return
        log_event(
            logger,
            "summarize_exit",
            outcome="reject",
            reason=ctx.tick_summarize_idle_reason,
        )
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
    if _gov_block and _stab_bypass and not bypass:
        log_event(
            logger,
            "stability.governance_bypass",
            mode=_stab_ctx.mode.value,
            div_codes=div_codes,
            gov_reason=gov_reason,
            anti_pause=_stab_ctx.anti_pause.reason,
        )
    elif _gov_block and bypass:
        log_event(
            logger,
            "scheduler.governance_bypass_debug",
            reasons=list(ranking_trace.reason_codes) + div_codes,
            cluster_id=fp,
        )
        log_pipeline_trace(
            logger,
            stage="scoring",
            cluster_id=fp,
            decision="proceed",
            reason="debug_bypass_governance",
            policy_matches=[str(p) for p in policy_matches][:16],
        )
    pipeline_decision = evaluate_cluster_for_pipeline(
        cluster,
        settings=settings,
        evolution=evo,
        topic_hint=identity.topic_hint,
        fingerprint=fp,
        combined_text=combined_text,
        channel_scores=channel_scores,
        feedback_stats=feedback_stats,
        duplicate_similarity_pct=None,
        entity_hits=len(ents),
        entity_norms=entity_norms,
    )
    if pipeline_decision.defer_to_next_tick and not bypass:
        inc("cadence_deferred_cluster")
        append_decision(
            runtime_dir=settings.runtime_state_dir,
            decision_type="cluster_defer",
            outcome="deferred",
            subject_id=fp,
            reason_codes=list(pipeline_decision.suppression_reasons)[:24],
            ranking_trace=ranking_trace.to_dict(),
            policy_matches=policy_matches,
            scoring_components={"relevance_total": pipeline_decision.relevance.total},
        )
        log_event(
            logger,
            "scheduler.cluster_deferred_cadence",
            reasons=list(pipeline_decision.suppression_reasons),
            relevance_total=pipeline_decision.relevance.total,
            event_kind=evo.kind,
        )
        append_timeline_event(
            settings.runtime_state_dir,
            "cluster_deferred_cadence",
            {
                "reasons": list(pipeline_decision.suppression_reasons)[:24],
                "relevance_total": pipeline_decision.relevance.total,
                "event_fingerprint": fp,
                "topic_hint": identity.topic_hint,
                "event_kind": str(evo.kind),
            },
        )
        log_pipeline_trace(
            logger,
            stage="scoring",
            cluster_id=fp,
            decision="suppress",
            reason="defer_cadence",
        )
        ctx.tick_summarize_idle_reason = (
            f"cluster_deferred:{(pipeline_decision.suppression_reasons[0] if pipeline_decision.suppression_reasons else 'cadence')[:120]}"
        )
        log_event(
            logger,
            "summarize_exit",
            outcome="reject",
            reason=ctx.tick_summarize_idle_reason,
        )
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
    if pipeline_decision.suppress and not bypass:
        append_decision(
            runtime_dir=settings.runtime_state_dir,
            decision_type="cluster_suppress",
            outcome="suppressed",
            subject_id=fp,
            reason_codes=list(pipeline_decision.suppression_reasons)[:24],
            ranking_trace=ranking_trace.to_dict(),
            policy_matches=policy_matches,
            scoring_components={"relevance_total": pipeline_decision.relevance.total},
        )
        record_suppression_ttl(
            settings.runtime_state_dir,
            fp,
            3600.0,
            reason=(pipeline_decision.suppression_reasons[0] if pipeline_decision.suppression_reasons else "pipeline"),
        )
        record_suppression_metric(
            settings.runtime_state_dir,
            pipeline_decision.suppression_reasons[0] if pipeline_decision.suppression_reasons else "pipeline",
        )
        inc("skipped_intelligence_suppress")
        log_event(
            logger,
            "scheduler.cluster_suppressed",
            reasons=list(pipeline_decision.suppression_reasons),
            relevance_total=pipeline_decision.relevance.total,
            event_kind=evo.kind,
        )
        append_timeline_event(
            settings.runtime_state_dir,
            "cluster_suppressed",
            {
                "reasons": list(pipeline_decision.suppression_reasons)[:24],
                "relevance_total": pipeline_decision.relevance.total,
                "event_fingerprint": fp,
                "topic_hint": identity.topic_hint,
                "event_kind": str(evo.kind),
            },
        )
        log_pipeline_trace(
            logger,
            stage="scoring",
            cluster_id=fp,
            decision="suppress",
            reason="pipeline_decision",
            extra={"reasons": list(pipeline_decision.suppression_reasons)[:12]},
        )
        ctx.tick_summarize_idle_reason = (
            f"cluster_suppress:{(pipeline_decision.suppression_reasons[0] if pipeline_decision.suppression_reasons else 'pipeline')[:120]}"
        )
        log_event(
            logger,
            "summarize_exit",
            outcome="reject",
            reason=ctx.tick_summarize_idle_reason,
        )
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
    if pipeline_decision.suppress and bypass:
        log_event(
            logger,
            "scheduler.pipeline_suppress_bypass_debug",
            reasons=list(pipeline_decision.suppression_reasons)[:16],
            cluster_id=fp,
        )
    log_pipeline_trace(
        logger,
        stage="scoring",
        cluster_id=fp,
        decision="proceed",
        reason=f"relevance_total={pipeline_decision.relevance.total}",
        policy_matches=[str(p) for p in policy_matches][:16],
    )
    append_decision(
        runtime_dir=settings.runtime_state_dir,
        decision_type="cluster_selected",
        outcome="proceed",
        subject_id=fp,
        reason_codes=list(ranking_trace.reason_codes)[:24],
        ranking_trace=ranking_trace.to_dict(),
        policy_matches=policy_matches,
    )
    record_topic_selected(settings.runtime_state_dir, identity.topic_hint)
    record_selection(
        settings.runtime_state_dir,
        topic_key=identity.topic_hint,
        channels=[str(p.channel_name or "") for p in cluster],
    )

    inc("clusters_created")

    truncate_raw_posts_for_openai(
        cluster,
        max_chars_per_post=settings.max_post_chars,
        log=logger,
    )
    ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl

    t_ai = time.perf_counter()
    from app.reliability.summarize_fallback import summarize_openai_or_fallback

    path = await summarize_openai_or_fallback(
        ctx,
        cluster=cluster,
        openai=openai,
        settings=settings,
        ai_gate_open=ai_gate_open,
        bypass=bypass,
        minimal_mode=is_minimal_pipeline_mode(),
    )
    ai_status = path.ai_status
    if path.rejected:
        log_pipeline_trace(
            logger,
            stage="ai_summarization",
            cluster_id=fp,
            decision="reject",
            reason=ctx.tick_summarize_idle_reason,
            ai_status=ai_status,
        )
        log_event(
            logger,
            "summarize_exit",
            outcome="reject",
            reason=ctx.tick_summarize_idle_reason,
        )
        ctx.tick_timings["openai_sec"] = time.perf_counter() - t_ai
        observe_histogram("summarize_duration_seconds", ctx.tick_timings["openai_sec"])
        return
    sc = path.summary
    if sc is None:
        ctx.tick_summarize_idle_reason = "ai_summarization:no_summarizer_result"
        log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
        ctx.tick_timings["openai_sec"] = time.perf_counter() - t_ai
        return
    post_text, used_ids, headline = sc.post_text, sc.used_ids, sc.headline
    _ai_exec_patch = sc.execution.to_draft_extras_patch()
    log_pipeline_trace(
        logger,
        stage="ai_summarization",
        cluster_id=fp,
        decision="proceed",
        ai_status=ai_status,
        extra={"model": sc.execution.model},
    )
    ctx.tick_timings["openai_sec"] = time.perf_counter() - t_ai
    observe_histogram("summarize_duration_seconds", ctx.tick_timings["openai_sec"])
    from app.runtime_activity import record_ai_success, record_fallback_success

    if pd.use_fallback:
        record_fallback_success()
    else:
        record_ai_success()

    if not used_ids or not post_text:
        ctx.tick_summarize_idle_reason = "ai_summarization:model_empty_or_no_ids"
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason="model_empty_or_no_ids",
            stage="post_openai",
        )
        log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
        return

    id_to_post: dict[int, RawPost] = {p.id: p for p in cluster}

    def _dedupe_used_for_sources(ids: list[int]) -> list[int]:
        seen_ids: set[int] = set()
        seen_cm: set[tuple[str, int]] = set()
        out: list[int] = []
        for i in ids:
            if i not in id_to_post or i in seen_ids:
                continue
            p = id_to_post[i]
            key = (str(p.channel_name).strip(), int(p.message_id))
            if key in seen_cm:
                continue
            seen_ids.add(i)
            seen_cm.add(key)
            out.append(i)
        return out

    used_ids = _dedupe_used_for_sources(used_ids)
    if not used_ids or not post_text:
        ctx.tick_summarize_idle_reason = "ai_summarization:empty_after_source_dedupe"
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason="empty_after_source_dedupe",
            stage="post_openai",
        )
        log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
        return

    used_posts = [id_to_post[i] for i in used_ids]
    from app.editorial.source_languages import text_violates_output_language, translation_context_for_cluster

    tctx = translation_context_for_cluster(used_posts, settings)
    # Hard guarantee: for multilingual sources (e.g. zh->ru), do not create a draft
    # if summarize output still contains CJK leakage.
    if tctx.get("translation_required") and text_violates_output_language(
        post_text,
        output_language=str(tctx.get("output_language") or "ru"),
    ):
        from app.editorial.translate_fallback import translate_zh_to_ru
        from app.publisher.draft_builder import finalize_draft_content, polish_channel_post

        lead_text = str((used_posts[0].text if used_posts else "") or post_text or "")
        fixed_ru = await translate_zh_to_ru(lead_text)
        if fixed_ru and not text_violates_output_language(
            fixed_ru,
            output_language=str(tctx.get("output_language") or "ru"),
        ):
            post_text = polish_channel_post(fixed_ru, max_chars=settings.max_post_chars)
            post_text = finalize_draft_content(post_text, max_chars=settings.max_post_chars)
            log_event(
                logger,
                "scheduler.translation_recovered_fallback",
                source_language=tctx.get("source_language"),
                output_language=tctx.get("output_language"),
            )
        else:
            skipped_ids = sorted({int(p.id) for p in used_posts if getattr(p, "id", None) is not None})
            if skipped_ids:
                try:
                    async with session_scope() as session:
                        await mark_raw_posts_processed(session, skipped_ids, utcnow())
                    log_event(
                        logger,
                        "scheduler.translation_reject_marked_processed",
                        skipped_raw_posts=len(skipped_ids),
                        source_language=tctx.get("source_language"),
                        output_language=tctx.get("output_language"),
                    )
                except Exception as exc:
                    log_event(
                        logger,
                        "scheduler.translation_reject_mark_processed_failed",
                        error=repr(exc)[:200],
                        skipped_raw_posts=len(skipped_ids),
                    )
            ctx.tick_summarize_idle_reason = (
                f"translation_failed_output_language:{tctx.get('source_language')}->{tctx.get('output_language')}"
            )
            log_event(
                logger,
                "scheduler.summarize_skipped",
                reason=ctx.tick_summarize_idle_reason,
                stage="post_openai",
            )
            log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
            return

    sources_payload: list[dict[str, object]] = [
        {
            "channel": p.channel_name,
            "message_id": p.message_id,
        }
        for p in used_posts
    ]

    _breaking_draft = ctx.is_breaking_stream or (
        desk is not None
        and escore is not None
        and (desk.breaking_override or desk.editorial_category == "breaking" or escore.is_breaking)
    )
    if _breaking_draft:
        from app.publisher.draft_builder import build_draft_body

        ctx.is_breaking_stream = True
        lead_post = used_posts[0] if used_posts else (cluster[0] if cluster else None)
        src_text = (lead_post.text if lead_post else None) or post_text
        draft_body = build_draft_body(
            src_text,
            breaking=True,
            sources=sources_payload,
            max_chars=settings.max_post_chars,
        )
    else:
        from app.editorial.compression_pipeline import build_compressed_draft_from_posts
        from app.publisher.draft_builder import format_single_source_draft

        # One source → readable blurb; prefer translated summary for zh→ru clusters.
        if len(used_posts) == 1:
            p = used_posts[0]
            if tctx.get("translation_required") and post_text:
                src_text = str(post_text)
            else:
                src_text = str(p.text or post_text or "")
            compressed = format_single_source_draft(
                {
                    "text": src_text,
                    "source": str(p.channel_name or ""),
                    "message_id": int(p.message_id),
                },
                max_chars=settings.max_post_chars,
                fallback_text=post_text,
            )
        else:
            compressed = build_compressed_draft_from_posts(
                used_posts if used_posts else cluster,
                fallback_text=post_text,
                runtime_dir=settings.runtime_state_dir,
                max_chars=settings.max_post_chars,
            )
        draft_body = compose_post_with_headline(settings, compressed, headline)
        log_event(
            logger,
            "draft.compression_applied",
            cluster_size=len(cluster),
            used_posts=len(used_posts),
        )
    from app.publisher.draft_builder import finalize_draft_content

    draft_body = finalize_draft_content(draft_body, max_chars=settings.max_post_chars)
    _stab_extras: dict[str, object] = {}
    try:
        from app.editorial.stability.controller import enrich_draft_for_stability

        _desk_cat = str(getattr(desk, "editorial_category", None) or "macro") if desk is not None else "macro"
        _desk_q = float(getattr(desk, "quality_score", 0.0) or 0.0) if desk is not None else 0.0
        _is_brk = bool(
            (escore is not None and getattr(escore, "is_breaking", False))
            or (desk is not None and getattr(desk, "breaking_override", False))
        )
        draft_body, _stab_extras = enrich_draft_for_stability(
            draft_body,
            runtime_dir=settings.runtime_state_dir,
            editorial_category=_desk_cat,
            quality_score=_desk_q,
            is_breaking=_is_brk,
            publishing_mode=_publishing_mode,
            sources=[str(p.channel_name or "") for p in cluster],
            cluster_size=len(cluster),
            cluster_texts=[str(p.text or "")[:2000] for p in (used_posts or cluster)],
            newsroom_tz=settings.newsroom_timezone,
        )
        try:
            from app.editorial.clean_channel_copy import prepare_clean_channel_post

            draft_body = prepare_clean_channel_post(
                draft_body,
                max_chars=settings.max_post_chars,
            )
        except Exception:
            pass
        if _stab_extras.get("stability_reject"):
            ctx.tick_summarize_idle_reason = "dominance_growth_reject"
            log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
            return
    except Exception as exc:
        log_event(logger, "stability.enrich_failed", error=repr(exc)[:200])
    content_hash = sha256_hex(draft_body)

    keys = {(str(p.channel_name).strip(), int(p.message_id)) for p in used_posts}
    raw_post_ids_for_db = sorted(
        {
            p.id
            for p in cluster
            if (str(p.channel_name).strip(), int(p.message_id)) in keys
        }
    )
    cadence_session_key = ""
    cadence_signature = ""
    cadence_decision_reason = ""

    # Guardrail: never send placeholder/empty or truncated teasers to moderation.
    from app.editorial.content_quality import passes_summarize_informative_gate
    from app.editorial.stability.anti_pause import evaluate_anti_pause

    normalized_body = " ".join(str(draft_body or "").split()).strip()
    _anti_pause = evaluate_anti_pause(newsroom_tz=settings.newsroom_timezone)
    _informative_ok = passes_summarize_informative_gate(
        normalized_body,
        publishing_mode=_publishing_mode,
        anti_pause_active=_anti_pause.anti_pause_active or _anti_pause.max_gap_exceeded,
    )
    if not _informative_ok:
        if raw_post_ids_for_db:
            try:
                async with session_scope() as session:
                    await mark_raw_posts_processed(session, raw_post_ids_for_db, utcnow())
            except Exception as exc:
                log_event(
                    logger,
                    "scheduler.informative_reject_mark_processed_failed",
                    error=repr(exc)[:200],
                )
        ctx.tick_summarize_idle_reason = "draft_not_informative_or_truncated"
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason=ctx.tick_summarize_idle_reason,
            normalized_len=len(normalized_body),
        )
        log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
        return

    if normalized_body in {"News update.", "News update"} or len(normalized_body) < 20:
        if raw_post_ids_for_db:
            try:
                async with session_scope() as session:
                    await mark_raw_posts_processed(session, raw_post_ids_for_db, utcnow())
            except Exception as exc:
                log_event(
                    logger,
                    "scheduler.empty_draft_mark_processed_failed",
                    error=repr(exc)[:200],
                    skipped_raw_posts=len(raw_post_ids_for_db),
                )
        ctx.tick_summarize_idle_reason = "draft_too_short_or_placeholder"
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason=ctx.tick_summarize_idle_reason,
            normalized_len=len(normalized_body),
        )
        log_event(
            logger,
            "summarize_exit",
            outcome="reject",
            reason=ctx.tick_summarize_idle_reason,
        )
        return

    cadence_enabled = os.getenv("GROWTH_CADENCE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if cadence_enabled and not bypass and not starvation_recovery:
        from app.editorial.stability.anti_pause import evaluate_anti_pause
        from app.editorial.stability.config import skip_cadence_cap_on_anti_pause

        _ap = evaluate_anti_pause(newsroom_tz=settings.newsroom_timezone)
        _skip_cadence = skip_cadence_cap_on_anti_pause() and _ap.anti_pause_active
        _priority_boost = bool(_stab_extras.get("priority_boost"))
        if not _skip_cadence and not _priority_boost:
            try:
                from app.editorial.growth_cadence import allow_story_for_current_session

                priority_score = float(getattr(escore, "final_priority_score", 0.0) or 0.0) if escore is not None else 0.0
                if desk is not None:
                    desk_q = float(getattr(desk, "quality_score", 0.0) or 0.0)
                    if desk_q > 0:
                        priority_score = max(priority_score, desk_q)
                is_breaking = bool(
                    (escore is not None and getattr(escore, "is_breaking", False))
                    or (desk is not None and getattr(desk, "breaking_override", False))
                )
                cadence_allowed, cadence_decision_reason, cadence_sess = allow_story_for_current_session(
                    runtime_dir=settings.runtime_state_dir,
                    priority_score=priority_score,
                    is_breaking=is_breaking,
                    newsroom_tz=settings.newsroom_timezone,
                )
                cadence_session_key = cadence_sess.key
                cadence_signature = cadence_sess.signature
                if not cadence_allowed:
                    if raw_post_ids_for_db:
                        try:
                            async with session_scope() as session:
                                await mark_raw_posts_processed(session, raw_post_ids_for_db, utcnow())
                        except Exception as exc:
                            log_event(
                                logger,
                                "scheduler.cadence_reject_mark_processed_failed",
                                error=repr(exc)[:200],
                            )
                    ctx.tick_summarize_idle_reason = f"growth_cadence:{cadence_decision_reason}"
                    log_event(
                        logger,
                        "scheduler.summarize_skipped",
                        reason=ctx.tick_summarize_idle_reason,
                        session=cadence_session_key,
                        priority_score=priority_score,
                    )
                    log_event(logger, "summarize_exit", outcome="reject", reason=ctx.tick_summarize_idle_reason)
                    return
            except Exception as exc:
                log_event(logger, "growth_cadence.evaluate_failed", error=repr(exc)[:200])

    observe_draft_quality(
        logger,
        settings,
        post_text=draft_body,
        used_ids=used_ids,
        sources_payload=sources_payload,
        cluster_size=len(cluster),
        content_hash=content_hash,
    )
    dedupe_since = utcnow() - timedelta(hours=settings.draft_dedupe_window_hours)
    published_dedupe_since = utcnow() - timedelta(
        hours=float(os.getenv("PUBLISHED_DEDUPE_WINDOW_HOURS", "96"))
    )

    t_dbw = time.perf_counter()
    editorial_intel: dict[str, object] | None = None
    extras_for_notify = "{}"
    async with session_scope() as session:
        recent = await fetch_recent_drafts_for_dedupe(
            session,
            limit=48,
            not_older_than=dedupe_since,
        )
        skip, reason = draft_should_be_skipped_as_duplicate(
            new_content=draft_body,
            new_hash=content_hash,
            recent=recent,
            similarity_threshold=settings.draft_similarity_threshold,
        )
        from app.editorial.burnin_governance import duplicate_strict_mode

        if skip and not bypass and duplicate_strict_mode():
            inc("skipped_duplicates")
            ctx.duplicate_skipped_this_tick = True
            record_duplicate_skip(logger, settings)
            log_event(logger, "draft.skipped_duplicate", reason=reason, hash_prefix=content_hash[:12])
            log_pipeline_trace(
                logger,
                stage="draft",
                cluster_id=fp,
                decision="suppress",
                reason=f"duplicate:{reason}",
            )
            append_timeline_event(
                settings.runtime_state_dir,
                "draft_skipped_duplicate",
                {"reason": reason, "hash_prefix": content_hash[:16], "topic_hint": identity.topic_hint},
            )
            try:
                from utils.source_reputation import record_duplicate_signal_for_channels
                from editorial.suppression_memory import bump_duplicate_burst

                record_duplicate_signal_for_channels(
                    [str(p.channel_name) for p in used_posts],
                    runtime_dir=settings.runtime_state_dir,
                )
                bump_duplicate_burst(settings.runtime_state_dir)
            except Exception:
                pass
            ctx.tick_summarize_idle_reason = f"draft_duplicate:{reason[:120]}"
            log_event(
                logger,
                "summarize_exit",
                outcome="reject",
                reason=ctx.tick_summarize_idle_reason,
            )
            ctx.tick_timings["db_draft_sec"] = time.perf_counter() - t_dbw
            return
        if skip and bypass:
            log_event(logger, "draft.duplicate_bypass_debug", reason=reason, cluster_id=fp)

        # Do not send Russian duplicates to moderation if similar content was already published.
        from app.editorial.source_languages import LANG_RU, detect_text_language

        if detect_text_language(draft_body) == LANG_RU:
            recent_published = await fetch_recent_published_for_dedupe(
                session,
                limit=64,
                not_older_than=published_dedupe_since,
            )
            pub_threshold = float(
                os.getenv("PUBLISHED_DUPLICATE_SIMILARITY_THRESHOLD", str(settings.draft_similarity_threshold))
            )
            pub_skip, pub_reason = draft_should_be_skipped_as_duplicate(
                new_content=draft_body,
                new_hash=content_hash,
                recent=recent_published,
                similarity_threshold=max(0.5, min(pub_threshold, 0.999)),
            )
            if pub_skip:
                await mark_raw_posts_processed(session, raw_post_ids_for_db, utcnow())
                inc("skipped_duplicates")
                ctx.duplicate_skipped_this_tick = True
                ctx.tick_summarize_idle_reason = f"published_duplicate:{pub_reason[:120]}"
                log_event(
                    logger,
                    "draft.skipped_published_duplicate",
                    reason=pub_reason,
                    hash_prefix=content_hash[:12],
                )
                log_event(
                    logger,
                    "summarize_exit",
                    outcome="reject",
                    reason=ctx.tick_summarize_idle_reason,
                )
                ctx.tick_timings["db_draft_sec"] = time.perf_counter() - t_dbw
                return

        log_event(logger, "draft_insert_started", cluster_id=fp, content_hash_prefix=content_hash[:12])
        draft = await create_draft_and_mark_posts_processed(
            session,
            content=draft_body,
            content_hash=content_hash,
            sources_payload=sources_payload,
            raw_post_ids=raw_post_ids_for_db,
        )
        draft_id = int(draft.id)
        scores = compute_quality_scores(
            post_text=draft_body,
            used_ids=used_ids,
            cluster_size=len(cluster),
        )
        await merge_draft_extras(session, draft_id, {"quality": scores})
        await merge_draft_extras(session, draft_id, correlation_fields_for_draft())
        from app.editorial.source_languages import translation_context_for_cluster

        await merge_draft_extras(
            session,
            draft_id,
            translation_context_for_cluster(used_posts, settings),
        )
        from publisher.draft_media import lead_media_from_raw_posts
        from publisher.media_pipeline import enrich_draft_media

        media_attach = lead_media_from_raw_posts(used_posts)
        _media_category = "news"
        if desk is not None:
            _media_category = str(getattr(desk, "editorial_category", None) or "news")
        try:
            media_res = await enrich_draft_media(
                runtime_dir=settings.runtime_state_dir,
                draft_body=draft_body,
                headline=(headline or ""),
                category=_media_category,
                used_posts=used_posts,
                sources_payload=sources_payload,
                existing_media=media_attach,
                draft_id=draft_id,
                openai_client=ctx.openai,
            )
            if media_res.extras_patch:
                await merge_draft_extras(session, draft_id, media_res.extras_patch)
            ctx.tick_media_detail = media_res.tick_detail_fields()
        except Exception as exc:
            log_event(logger, "media.pipeline_failed", draft_id=draft_id, error=repr(exc)[:200])
            ctx.tick_media_detail = {
                "media_status": "failed",
                "media_type": "none",
                "media_fallback": False,
            }
        await merge_draft_extras(session, draft_id, _ai_exec_patch)
        if cadence_enabled:
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "growth_cadence": {
                        "session": cadence_session_key,
                        "signature": cadence_signature,
                        "decision_reason": cadence_decision_reason or "allowed",
                    }
                },
            )
        if _stab_extras.get("ccd"):
            await merge_draft_extras(session, draft_id, {"ccd": _stab_extras["ccd"]})
        if _stab_extras.get("mpaes"):
            await merge_draft_extras(session, draft_id, {"mpaes": _stab_extras["mpaes"]})
        if _stab_extras.get("ugsol"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "ugsol": _stab_extras["ugsol"],
                    "final_editorial_decision": _stab_extras.get("final_editorial_decision"),
                },
            )
        if _stab_extras.get("gmcs"):
            await merge_draft_extras(session, draft_id, {"gmcs": _stab_extras["gmcs"]})
        if _stab_extras.get("eml"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "eml": _stab_extras["eml"],
                    "editorial_monetization": _stab_extras.get("editorial_monetization"),
                },
            )
        if _stab_extras.get("eaa"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "eaa": _stab_extras["eaa"],
                    "ai_editorial_review": _stab_extras.get("ai_editorial_review"),
                    "autonomous_publish_approved": _stab_extras.get("autonomous_publish_approved"),
                },
            )
        if _stab_extras.get("osgcp"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "osgcp": _stab_extras["osgcp"],
                    "flagship_post": bool(_stab_extras.get("flagship_post")),
                    "priority_boost": bool(_stab_extras.get("priority_boost")),
                    "force_digest_slot": bool(_stab_extras.get("force_digest_slot")),
                },
            )
        elif _stab_extras.get("product_os"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "product_os": _stab_extras["product_os"],
                    "channel_product": _stab_extras.get("channel_product") or {},
                    "growth": _stab_extras.get("growth") or {},
                    "flagship_post": bool(_stab_extras.get("flagship_post")),
                    "priority_boost": bool(_stab_extras.get("priority_boost")),
                    "force_digest_slot": bool(_stab_extras.get("force_digest_slot")),
                },
            )
        elif _stab_extras.get("channel_product"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "channel_product": _stab_extras["channel_product"],
                    "growth": _stab_extras.get("growth") or {},
                },
            )
        if _stab_extras.get("ueos"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "ueos": _stab_extras["ueos"],
                    "flagship_post": bool(_stab_extras.get("flagship_post")),
                    "priority_boost": bool(_stab_extras.get("priority_boost")),
                    "force_digest_slot": bool(_stab_extras.get("force_digest_slot")),
                },
            )
        if _stab_extras.get("audience_unification"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "audience_unification": _stab_extras["audience_unification"],
                    "flagship_post": bool(_stab_extras.get("flagship_post")),
                },
            )
        if _stab_extras.get("editorial_dominance"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "editorial_dominance": _stab_extras["editorial_dominance"],
                    "priority_boost": bool(_stab_extras.get("priority_boost")),
                    "force_digest_slot": bool(_stab_extras.get("force_digest_slot")),
                },
            )
        if _stab_extras.get("editorial_stability"):
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "editorial_stability": _stab_extras["editorial_stability"],
                    "publishing_mode": _publishing_mode,
                },
            )
        ed_card = compute_editorial_score_card(
            draft_text=draft_body,
            raw_posts=used_posts,
            quality_scores=scores,
            cluster_size=len(cluster),
        )
        await merge_draft_extras(session, draft_id, {"editorial_scores": ed_card.to_dict()})
        intel = await draft_duplicate_intel(
            session,
            draft_id,
            similarity_threshold=settings.draft_similarity_threshold,
            window_hours=settings.draft_dedupe_window_hours,
        )
        await merge_draft_extras(session, draft_id, {"duplicate_intel": intel})
        await session.commit()
        log_event(logger, "draft_insert_committed", draft_id=draft_id, cluster_id=fp)

        cohesion_val = avg_pairwise_lexical_cohesion(cluster)
        ecluster = build_event_cluster(cluster, cohesion=cohesion_val)
        max_dup_pct = float(intel.get("max_similarity_pct") or 0.0)
        dup_for_conf = max(float(ed_card.duplicate_confidence), max_dup_pct / 100.0)
        ed_conf = compute_editorial_confidence(
            source_count=len(used_posts),
            unique_channels=len({str(p.channel_name).strip().lower() for p in used_posts if str(p.channel_name).strip()}),
            editorial_scores=ed_card.to_dict(),
            ai_generation=_ai_exec_patch.get("ai_generation") if isinstance(_ai_exec_patch, dict) else None,
            duplicate_confidence=dup_for_conf,
        )
        hq_headline = (headline or "").strip() if settings.headline_mode == "json" else ""
        if not hq_headline and draft_body:
            hq_headline = (draft_body.split("\n", 1)[0]).strip()[:220]
        hq_eval = evaluate_headline_quality(hq_headline, body_excerpt=(draft_body or "")[:800])
        trend_snap = detect_topic_trends(settings.runtime_state_dir)
        await merge_draft_extras(
            session,
            draft_id,
            {
                "cluster_intelligence": {
                    "event_identity": identity.to_dict(),
                    "event_evolution": evo.to_dict(),
                    "event_cluster": ecluster.to_dict(),
                    "pipeline_decision": pipeline_decision.to_dict(),
                    "editorial_hold": pipeline_decision.hold_for_review,
                    "editorial_escalate": pipeline_decision.escalate_priority,
                    "entities": [
                        {"kind": e.kind, "normalized": e.normalized, "text": (e.text or "")[:120]} for e in ents[:32]
                    ],
                    "duplicate_max_similarity_pct": max_dup_pct,
                    "trends_snapshot": trend_snap,
                    "source_convergence": round(source_convergence_score(used_posts), 4),
                },
                "editorial_confidence": ed_conf.to_dict(),
                "headline_quality": hq_eval,
                "editorial_governance": build_draft_governance_metadata(
                    runtime_dir=settings.runtime_state_dir,
                    posts=used_posts,
                    topic_hint=identity.topic_hint,
                    fingerprint=fp,
                    ranking_trace=ranking_trace,
                    pipeline_decision=pipeline_decision.to_dict(),
                    policy_matches=policy_matches,
                    selection_reasons=list(ranking_trace.reason_codes),
                ),
            },
        )
        append_event_history(
            settings.runtime_state_dir,
            fingerprint=fp,
            combined_text_excerpt=combined_text[:4000],
        )

        from ai.breaking_news import detect_breaking_news
        from ai.editorial_priority import compute_editorial_priority
        from ai.editorial_tags import infer_editorial_tags
        from ai.editorial_titles import generate_title_suggestions

        recent_sim = sum(
            1
            for r in (intel.get("related") or [])
            if isinstance(r, dict) and float(r.get("similarity_pct") or 0.0) > 85.0
        )
        rep = export_channel_scores_for_priority(settings.runtime_state_dir)
        tag_payload = infer_editorial_tags(draft_body, sources_payload)
        pri = compute_editorial_priority(
            draft_body,
            sources_payload,
            duplicate_intel=intel,
            quality_scores=scores,
            source_reputation=rep,
        )
        brk = detect_breaking_news(
            content=draft_body,
            sources=sources_payload,
            duplicate_intel=intel,
            priority=pri,
            recent_similar_count=recent_sim,
        )
        titles = generate_title_suggestions(draft_body)
        inf_tags = tag_payload.get("inferred_tags") or []
        if not isinstance(inf_tags, list):
            inf_tags = []
        narrative_intel: dict[str, Any] | None = None
        if escore is not None:
            try:
                from app.editorial.intelligence.trend_memory import (
                    evaluate_narrative_strategy,
                    observe_narrative_event,
                )
                from app.editorial.signal_ranking import rank_story_signal
                from app.growth_layer.virality.engine import growth_layer_enabled

                _chans = [
                    str(s.get("channel") or "")
                    for s in sources_payload
                    if isinstance(s, dict) and str(s.get("channel") or "").strip()
                ]
                _cat = str(tag_payload.get("category") or "general")
                _signal = rank_story_signal(
                    draft_body,
                    escore,
                    sources=_chans,
                    runtime_dir=settings.runtime_state_dir,
                    category=_cat,
                )
                if growth_layer_enabled():
                    try:
                        from app.growth_layer.format.profiles import resolve_publish_format_profile
                        from app.growth_layer.virality.engine import ViralityScoreEngine
                        from db.growth_scores_repository import upsert_draft_growth_score

                        _vir = ViralityScoreEngine().score(
                            text=draft_body,
                            signal=_signal,
                            escore=escore,
                            editorial_card=ed_card.to_dict() if ed_card is not None else None,
                        )
                        _fmt_profile = resolve_publish_format_profile(
                            _vir.score,
                            draft_id=draft_id,
                            content=draft_body,
                        )
                        await upsert_draft_growth_score(
                            session,
                            draft_id=draft_id,
                            result=_vir,
                            format_profile=_fmt_profile,
                        )
                        await merge_draft_extras(
                            session,
                            draft_id,
                            _vir.to_growth_extras_patch(format_profile=_fmt_profile),
                        )
                        log_event(
                            logger,
                            "growth.virality_scored",
                            draft_id=draft_id,
                            virality_score=_vir.score,
                            virality_tier=_vir.tier.value,
                            format_profile=_fmt_profile,
                        )
                    except Exception as exc:
                        log_event(
                            logger,
                            "growth.virality_score_failed",
                            draft_id=draft_id,
                            error=repr(exc)[:200],
                        )
                narrative_intel = evaluate_narrative_strategy(
                    settings.runtime_state_dir,
                    text=draft_body,
                    category=_cat,
                )
                narrative_intel["cluster_key"] = _signal.narrative_cluster or narrative_intel.get("cluster_key")
                narrative_intel["signal_priority_multiplier"] = _signal.priority_multiplier
                observe_narrative_event(
                    settings.runtime_state_dir,
                    text=draft_body,
                    category=_cat,
                    repost_rate=_signal.repost_probability,
                    forward_velocity=_signal.forwardability,
                    open_retention=min(1.0, _signal.narrative_strength * 0.6 + _signal.repost_probability * 0.4),
                    reaction_density=_signal.reaction_potential,
                    quoteability=_signal.quoteability,
                    screenshot_probability=_signal.screenshotability,
                    engagement_longevity=min(1.0, _signal.novelty * 0.5 + _signal.shareability * 0.5),
                    hashtags=[str(t) for t in inf_tags[:3]],
                    hook_variant=f"{_cat}_default",
                )
            except Exception as exc:
                log_event(logger, "narrative_trend.observe_failed", error=repr(exc)[:200])
        await merge_draft_extras(
            session,
            draft_id,
            {
                "editorial_tags": {
                    "category": tag_payload.get("category"),
                    "category_confidence": tag_payload.get("category_confidence"),
                    "category_reasoning": tag_payload.get("category_reasoning"),
                    "inferred_tags": inf_tags,
                },
                "category": tag_payload.get("category"),
                "category_confidence": tag_payload.get("category_confidence"),
                "category_reasoning": tag_payload.get("category_reasoning"),
                "inferred_tags": inf_tags,
                "tags": [str(t) for t in inf_tags][:24],
                "priority": pri,
                "breaking": brk,
                "title_suggestions": titles,
                "narrative_intelligence": narrative_intel or {},
            },
        )
        if brk.get("is_breaking"):
            append_runtime_event(
                "draft_breaking_signal",
                message="candidate",
                draft_id=draft_id,
                breaking_score=float(brk.get("breaking_score") or 0.0),
            )
            inc("editorial_breaking_detected")

        pol_eff, _ = resolve_effective_policy(load_editorial_policy_bundle(settings), dominant_channel_key(used_posts))
        uniq_src = len(
            {
                str(s.get("channel") or "").strip().lower()
                for s in sources_payload
                if isinstance(s, dict) and str(s.get("channel") or "").strip()
            }
        )
        unique_ratio = uniq_src / max(1, len(sources_payload))
        pub_pri = compute_publication_priority_score(
            breaking_block=brk if isinstance(brk, dict) else None,
            evolution_kind=str(evo.kind),
            duplicate_max_pct=max_dup_pct,
            editorial_priority=pri if isinstance(pri, dict) else None,
        )
        try:
            gate_block, gate_reasons = evaluate_publish_gate(
                settings,
                settings.runtime_state_dir,
                pol_eff,
                topic_key=topic_dedupe_key(identity.topic_hint),
                is_breaking=bool(brk.get("is_breaking")),
            )
        except Exception as gate_exc:
            log_event(
                logger,
                "publish_gate.evaluate_failed",
                draft_id=draft_id,
                error=repr(gate_exc)[:200],
                recovery="treat_as_blocked",
            )
            gate_block, gate_reasons = True, [f"cadence_gate_error:{type(gate_exc).__name__}"]
        ready = compute_publish_readiness_score(
            cadence_blocked=gate_block,
            confidence_score=ed_conf.confidence_score,
            headline_quality_score=float(hq_eval.get("score")) if hq_eval.get("score") is not None else None,
            unique_sources_ratio=unique_ratio,
        )
        await merge_draft_extras(
            session,
            draft_id,
            {
                "publication_intel": {
                    "publication_priority": pub_pri,
                    "publish_readiness": ready,
                    "cadence_gate_preview": {"blocked": gate_block, "reasons": gate_reasons},
                }
            },
        )
        if desk is not None and escore is not None:
            from app.editorial.identity import load_editorial_identity
            from app.editorial.publish_policy import evaluate_publish_policy

            _chans = [
                str(s.get("channel") or "")
                for s in sources_payload
                if isinstance(s, dict) and str(s.get("channel") or "").strip()
            ]
            _policy = evaluate_publish_policy(
                combined_text or draft_body,
                escore,
                desk,
                sources=_chans,
                runtime_dir=settings.runtime_state_dir,
            )
            from app.editorial.trust_system import evaluate_editorial_trust

            _trust = evaluate_editorial_trust(
                combined_text or draft_body,
                escore,
                sources=_chans,
                runtime_dir=settings.runtime_state_dir,
            )
            await merge_draft_extras(
                session,
                draft_id,
                {
                    "newsroom_product": {
                        "publish_policy": _policy.to_dict(),
                        "editorial_trust": _trust.to_dict(),
                        "identity": load_editorial_identity().to_dict(),
                        "manual_review_required": _policy.manual_review_required,
                        "auto_publish_eligible": _policy.auto_publish_eligible,
                    }
                },
            )
            try:
                if _policy.manual_review_required:
                    inc("manual_review_required_total")
                if _policy.auto_publish_eligible:
                    inc("auto_publish_eligible_total")
            except Exception:
                pass

        src_conv = round(source_convergence_score(used_posts), 4)
        if settings.quality_scoring_enabled:
            from editorial.scoring.service import enrich_draft_editorial_intelligence

            t_score = time.perf_counter()
            editorial_intel = await enrich_draft_editorial_intelligence(
                session,
                draft_id=draft_id,
                draft_text=draft_body,
                used_posts=used_posts,
                cluster_size=len(cluster),
                sources_payload=sources_payload,
                quality_scores=scores,
                duplicate_intel=intel,
                editorial_scores_card=ed_card.to_dict(),
                publication_priority=pub_pri if isinstance(pub_pri, dict) else None,
                editorial_priority=pri if isinstance(pri, dict) else None,
                runtime_dir=settings.runtime_state_dir,
                source_convergence=src_conv,
                timeout_sec=settings.editorial_scoring_timeout_sec,
                enabled=True,
            )
            scoring_sec = time.perf_counter() - t_score
            ctx.tick_timings["scoring_sec"] = scoring_sec
            observe_histogram("scoring_duration_seconds", scoring_sec)
            try:
                from ops.economics.resource_accounting import record_resource

                record_resource(settings.runtime_state_dir, stage="scoring", duration_sec=scoring_sec, count=1)
            except Exception:
                pass
            if editorial_intel:
                await merge_draft_extras(
                    session,
                    draft_id,
                    {"editorial_intelligence": editorial_intel},
                )

        draft_row = await get_draft_by_id(session, draft_id)
        extras_for_notify = (draft_row.draft_extras if draft_row else "{}") or "{}"
        log_event(logger, "pipeline_commit_completed", draft_id=draft_id, cluster_id=fp)

    inc("drafts_generated")
    ctx.tick_draft_id = draft_id
    from app.recovery.pipeline_state_reconciler import note_successful_summarize_tick

    note_successful_summarize_tick(draft_created=True)
    log_event(
        logger,
        "summarize_exit",
        outcome="draft_created",
        draft_id=draft_id,
        cluster_id=fp,
    )
    log_event(
        logger,
        "draft.created",
        draft_id=draft_id,
        raw_posts_used=len(raw_post_ids_for_db),
        content_hash_prefix=content_hash[:12],
    )
    logger.info("draft generated: draft_id=%s cluster_id=%s", draft_id, fp)
    log_pipeline_trace(
        logger,
        stage="draft",
        cluster_id=fp,
        decision="proceed",
        draft_id=draft_id,
    )

    if debug:
        await _force_publish_debug(ctx, draft_id=draft_id, cluster_id=fp)

    t_no = time.perf_counter()
    try:
        from app.ops.autonomous_publish import autonomous_editorial_mode_enabled, try_immediate_autonomous_publish

        if autonomous_editorial_mode_enabled():
            async with session_scope() as session:
                scheduled = await try_immediate_autonomous_publish(
                    settings,
                    session,
                    draft_id,
                    openai_client=ctx.openai,
                )
                if scheduled:
                    await session.commit()
                    append_runtime_event(
                        "draft_ai_approved_scheduled",
                        message="autonomous_publish",
                        draft_id=draft_id,
                    )
                    append_timeline_event(
                        settings.runtime_state_dir,
                        "draft_autonomous_scheduled",
                        {"draft_id": draft_id},
                    )
                else:
                    append_runtime_event(
                        "draft_ai_review_pending",
                        message="not_scheduled",
                        draft_id=draft_id,
                    )
        else:
            sources_display = json.dumps(sources_payload, ensure_ascii=False, indent=2)
            await notify_admin_new_draft(
                bot,
                settings,
                draft_id=draft_id,
                content=draft_body,
                sources=sources_display,
                editorial_intelligence=editorial_intel if isinstance(editorial_intel, dict) else None,
                draft_extras_json=extras_for_notify,
            )
            append_runtime_event(
                "draft_pending_moderation",
                message="queued_for_review",
                draft_id=draft_id,
            )
            append_timeline_event(
                settings.runtime_state_dir,
                "draft_created",
                {
                    "draft_id": draft_id,
                    "event_fingerprint": fp,
                    "topic_hint": identity.topic_hint,
                    "relevance_total": pipeline_decision.relevance.total,
                    "escalate": bool(pipeline_decision.escalate_priority),
                    "hold": bool(pipeline_decision.hold_for_review),
                },
            )
    except Exception as exc:
        logger.exception("Failed to notify admin about draft %s: %s", draft_id, exc)
        inc("admin_notify_failures")
        log_event(logger, "draft.notify_admin_failed", draft_id=draft_id, error=repr(exc))
    finally:
        ctx.tick_timings["notify_admin_sec"] = time.perf_counter() - t_no


async def _force_publish_debug(ctx: PipelineContext, *, draft_id: int, cluster_id: str) -> None:
    from app.pipeline_debug import (
        is_force_single_publish_env,
        mark_force_single_publish_done,
        pipeline_debug_active,
    )
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow
    from scheduler.pipeline_trace import log_pipeline_trace

    if not pipeline_debug_active(ctx.settings):
        return
    res = await execute_admin_publication_flow(
        ctx.bot,
        ctx.settings,
        draft_id,
        idempotency_key=f"debug:{cluster_id}:{draft_id}",
        bypass_cadence=True,
        bypass_leadership=True,
    )
    outcome = res.outcome.value
    if res.outcome is PublishFlowOutcome.OK:
        ctx.tick_publish_outcome = f"ok:draft_id={draft_id}:message_id={res.channel_message_id}"
        logger.info("publish succeeded: draft_id=%s channel_message_id=%s", draft_id, res.channel_message_id)
        log_pipeline_trace(
            logger,
            stage="publish",
            cluster_id=cluster_id,
            decision="proceed",
            publish_result=f"ok:message_id={res.channel_message_id}",
            draft_id=draft_id,
        )
        if is_force_single_publish_env() or getattr(ctx.settings, "force_single_publish", False):
            mark_force_single_publish_done(ctx.settings.runtime_state_dir)
    else:
        ctx.tick_publish_outcome = f"{outcome}:{(res.error or '')[:120]}"
        logger.warning("publish failed: draft_id=%s outcome=%s", draft_id, outcome)
        log_pipeline_trace(
            logger,
            stage="publish",
            cluster_id=cluster_id,
            decision="suppress",
            publish_result=f"{outcome}:{(res.error or '')[:120]}",
            draft_id=draft_id,
        )


async def _scheduled_publish_step(ctx: PipelineContext) -> None:
    from app.state.pipeline_execution_wrapper import execute_pipeline_step

    await execute_pipeline_step(
        ctx,
        "publish",
        lambda: _scheduled_publish_step_impl(ctx),
        require_should_execute=False,
        skip_reason_attr="tick_publish_outcome",
    )


async def _scheduled_publish_step_impl(ctx: PipelineContext) -> None:
    from app.state.pipeline_execution_wrapper import require_pipeline_wrapper_active

    require_pipeline_wrapper_active("scheduled_publish")
    t0 = time.perf_counter()
    settings = ctx.settings
    ctx.tick_timings["scheduled_publish_sec"] = 0.0
    from app.pipeline_debug import pipeline_debug_active
    from app.recovery.pipeline_overrides import is_force_publish_bypass, is_minimal_pipeline_mode
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    publish_bypass = (
        pipeline_debug_active(settings)
        or is_minimal_pipeline_mode()
        or is_force_publish_bypass()
    )
    if settings.dry_run and not publish_bypass:
        ctx.tick_publish_outcome = "skipped_dry_run"
        _log_pipeline_idle("publish", ctx.tick_publish_outcome)
        return

    bot = ctx.bot
    async with session_scope() as session:
        ids = await list_due_scheduled_draft_ids(session, limit=3)
    autonomous_publish_ids: set[int] = set()
    starvation_auto_publish = os.getenv("DESK_STARVATION_AUTO_PUBLISH", "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not ids:
        try:
            from app.ops.autonomous_publish import detect_publish_stall_risk, try_auto_schedule_one_pending

            async with session_scope() as session:
                try:
                    stall = await detect_publish_stall_risk(settings, session)
                    if stall.get("level") == "high":
                        log_event(
                            logger,
                            "publish.stall_alert",
                            level="high",
                            minutes_since_last_published=stall.get("minutes_since_last_published"),
                            pending_backlog=stall.get("pending_backlog"),
                            incoming_raw_flow_30m=stall.get("incoming_raw_flow_30m"),
                        )
                except Exception as exc:
                    log_event(logger, "publish.stall_check_failed", error=repr(exc)[:200])
                max_auto = int(os.getenv("AUTO_PUBLISH_MAX_SCHEDULE_PER_TICK", "2").strip() or "2")
                max_auto = max(1, min(5, max_auto))
                picked: list[int] = []
                for _ in range(max_auto):
                    auto_did = await try_auto_schedule_one_pending(settings, session)
                    if not auto_did or auto_did in autonomous_publish_ids:
                        break
                    picked.append(auto_did)
                    autonomous_publish_ids.add(auto_did)
                if picked:
                    await session.commit()
                    ids = picked
        except Exception as exc:
            log_event(logger, "auto_publish.schedule_failed", error=repr(exc)[:200])
    if starvation_auto_publish and not ids:
        try:
            from app.editorial.desk_starvation import desk_threshold_context
            from db.repository import approve_draft, list_pending_drafts, schedule_draft_publish, utcnow

            if desk_threshold_context().publish_starvation_detected:
                async with session_scope() as session:
                    pending = await list_pending_drafts(session, limit=1)
                    if pending:
                        did = int(pending[0].id)
                        if await approve_draft(session, did):
                            await schedule_draft_publish(session, did, when=utcnow())
                            await session.commit()
                            ids = [did]
                            autonomous_publish_ids.add(did)
                            log_event(
                                logger,
                                "desk.starvation_auto_publish",
                                draft_id=did,
                                recovery="approved_and_scheduled",
                            )
        except Exception as exc:
            log_event(logger, "desk.starvation_auto_publish_failed", error=repr(exc)[:200])
    if publish_bypass and not ids:
        from db.repository import list_pending_drafts

        async with session_scope() as session:
            pending = await list_pending_drafts(session, limit=1)
        if pending:
            ids = [int(pending[0].id)]
    # Guaranteed publishing floor: when every normal path produced nothing and
    # the channel has been silent past the hard ceiling, force one trustworthy
    # post in safety-only mode so algorithm/editorial changes can never silence
    # the channel for a prolonged period.
    floor_publish_ids: set[int] = set()
    if not ids:
        try:
            from app.ops.autonomous_publish import select_floor_publish_candidate

            async with session_scope() as session:
                cand = await select_floor_publish_candidate(settings, session)
            if cand:
                fid = int(cand["draft_id"])
                ids = [fid]
                floor_publish_ids.add(fid)
                log_event(
                    logger,
                    "publish.floor_triggered",
                    draft_id=fid,
                    minutes_since_last_published=cand.get("minutes_since"),
                    pending_backlog=cand.get("pending_backlog"),
                    incoming_raw_flow_30m=cand.get("incoming_raw_flow_30m"),
                )
        except Exception as exc:
            log_event(logger, "publish.floor_failed", error=repr(exc)[:200])
    published_ok = False
    for did in ids:
        bypass = publish_bypass or did in autonomous_publish_ids
        is_floor = did in floor_publish_ids
        res = await execute_admin_publication_flow(
            bot,
            settings,
            did,
            bypass_cadence=bypass or is_floor,
            bypass_leadership=bypass or is_floor,
            floor_publish=is_floor,
        )
        if res.outcome is PublishFlowOutcome.OK:
            published_ok = True
            ctx.tick_publish_outcome = f"ok:draft_id={did}:message_id={res.channel_message_id}"
            logger.info("publish succeeded: draft_id=%s channel_message_id=%s", did, res.channel_message_id)
            inc("scheduled_publish_fired")
            append_runtime_event("scheduled_publish_ok", message="published", draft_id=did)
        elif res.outcome is PublishFlowOutcome.SEND_FAILED:
            ctx.tick_publish_outcome = f"failed:{res.error or 'send_failed'}"[:200]
            logger.warning("publish failed: draft_id=%s error=%s", did, (res.error or "")[:200])
            append_runtime_event(
                "scheduled_publish_failed",
                message=(res.error or "")[:300],
                draft_id=did,
            )
        else:
            ctx.tick_publish_outcome = f"{res.outcome.value}:draft_id={did}"
            logger.info("publish not sent: draft_id=%s outcome=%s", did, res.outcome.value)
    # Guaranteed floor (post-attempt): the pre-loop floor only fires when no draft
    # was *selected*. But the autonomous path may select a fresh draft every tick
    # that the editorial gate then denies (e.g. "low-signal" fallback summaries),
    # which would keep the channel silent indefinitely. So if nothing actually
    # published and silence has passed the hard ceiling, ship one safe item in
    # safety-only mode (which also re-uses the freshest just-denied draft).
    if not published_ok and not floor_publish_ids:
        try:
            from app.ops.autonomous_publish import select_floor_publish_candidate

            async with session_scope() as session:
                cand = await select_floor_publish_candidate(settings, session)
            if cand:
                fid = int(cand["draft_id"])
                log_event(
                    logger,
                    "publish.floor_triggered",
                    draft_id=fid,
                    recovery="post_denied",
                    minutes_since_last_published=cand.get("minutes_since"),
                    pending_backlog=cand.get("pending_backlog"),
                    incoming_raw_flow_30m=cand.get("incoming_raw_flow_30m"),
                )
                res = await execute_admin_publication_flow(
                    bot,
                    settings,
                    fid,
                    bypass_cadence=True,
                    bypass_leadership=True,
                    floor_publish=True,
                )
                if res.outcome is PublishFlowOutcome.OK:
                    published_ok = True
                    ctx.tick_publish_outcome = (
                        f"ok:draft_id={fid}:message_id={res.channel_message_id}"
                    )
                    logger.info(
                        "publish floor succeeded: draft_id=%s channel_message_id=%s",
                        fid,
                        res.channel_message_id,
                    )
                    inc("scheduled_publish_fired")
                    append_runtime_event(
                        "scheduled_publish_ok", message="floor_published", draft_id=fid
                    )
                else:
                    logger.info(
                        "publish floor not sent: draft_id=%s outcome=%s", fid, res.outcome.value
                    )
        except Exception as exc:
            log_event(logger, "publish.floor_failed", error=repr(exc)[:200])
    if ctx.tick_publish_outcome == "not_reached":
        _log_pipeline_idle("publish", "no_due_drafts_or_no_pending")
    ctx.tick_timings["scheduled_publish_sec"] = time.perf_counter() - t0
    observe_histogram("publish_duration_seconds", ctx.tick_timings["scheduled_publish_sec"])


async def run_operational_heartbeat(ctx: PipelineContext) -> None:
    from app.runtime_watchdog import run_watchdog_checks
    from editorial.governance.drift import check_editorial_drift

    await log_runtime_diagnostics(logger, ctx.settings)
    await run_watchdog_checks(ctx.settings, collector_enabled=ctx.collector_enabled)
    check_editorial_drift(ctx.settings.runtime_state_dir, logger=logger)
    try:
        from ops.resilience.lifecycle_retention import run_lifecycle_retention

        run_lifecycle_retention(ctx.settings.runtime_state_dir)
    except Exception as exc:
        logger.warning("lifecycle_retention skipped: %s", exc)
    try:
        from ops.analytics.publication import update_rollup_from_runtime
        from ops.operator_notifications import flush_pending_notifications

        update_rollup_from_runtime(ctx.settings.runtime_state_dir)
        await flush_pending_notifications(ctx.bot, ctx.settings)
    except Exception as exc:
        logger.warning("operator_ops_heartbeat skipped: %s", exc)
    try:
        from app.reliability.auto_maintenance import evaluate_auto_maintenance
        from app.reliability.failed_draft_recovery import run_failed_draft_retry_batch
        from app.reliability.pipeline_watchdog import run_pipeline_watchdog
        from app.reliability.stuck_publishing_recovery import recover_stuck_publishing_batch
        from app.reliability.sqlite_ops import run_sqlite_integrity_check

        from app.reliability.invariants import run_heartbeat_invariant_checks

        await run_heartbeat_invariant_checks(ctx.settings)
        await run_pipeline_watchdog(ctx.settings, collector_enabled=ctx.collector_enabled)
        await recover_stuck_publishing_batch(ctx.settings, limit=8)
        from app.observability.runtime_protection import retry_batch_limit

        await run_failed_draft_retry_batch(
            ctx.bot, ctx.settings, limit=retry_batch_limit(4, ctx.settings.runtime_state_dir)
        )
        await evaluate_auto_maintenance(ctx.settings)
        try:
            from app.ops.launch_control import enforce_launch_safety

            ls = enforce_launch_safety()
            if not ls.get("valid", True):
                log_event(logger, "launch_control.invalid_state", errors=ls.get("errors"))
        except Exception as exc:
            log_event(logger, "launch_control.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.runtime_protection import evaluate_and_apply_protection

            evaluate_and_apply_protection(ctx.settings.runtime_state_dir, settings=ctx.settings)
        except Exception as exc:
            log_event(logger, "runtime_protection.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.publish_continuity import run_continuity_checks_and_alert

            await run_continuity_checks_and_alert(ctx.settings)
        except Exception as exc:
            log_event(logger, "publish_continuity.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.telegram_production import run_telegram_production_checks_and_alert

            await run_telegram_production_checks_and_alert(ctx.settings, ctx.bot)
        except Exception as exc:
            log_event(logger, "telegram_production.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.burnin_validation import run_burnin_validation_heartbeat

            await run_burnin_validation_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "burnin_validation.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.public_traffic_monitor import run_public_traffic_heartbeat

            await run_public_traffic_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "public_traffic_monitor.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.editorial.post_quality_monitor import run_post_quality_heartbeat

            await run_post_quality_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "post_quality_monitor.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.production_safety_assertions import run_production_safety_assertions_heartbeat

            await run_production_safety_assertions_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "production_safety_assertions.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.ops.public_incident_safety import evaluate_incident_safety

            evaluate_incident_safety(ctx.settings.runtime_state_dir, settings=ctx.settings)
        except Exception as exc:
            log_event(logger, "public_incident_safety.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.ops.operator_incident_summary import run_operator_incident_summary_heartbeat

            await run_operator_incident_summary_heartbeat(ctx.settings, bot=ctx.bot)
        except Exception as exc:
            log_event(logger, "operator_incident_summary.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.observability.release_metadata import run_release_metadata_heartbeat

            await run_release_metadata_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "release_metadata.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.testing.e2e_pipeline_validator import run_e2e_validation_heartbeat
            from app.testing.telegram_live_simulation import run_telegram_live_simulation_heartbeat
            from app.observability.final_stability_report import run_final_stability_report_heartbeat

            await run_e2e_validation_heartbeat(ctx.settings)
            await run_telegram_live_simulation_heartbeat(ctx.settings)
            await run_final_stability_report_heartbeat(ctx.settings)
        except Exception as exc:
            log_event(logger, "final_integration.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.ops.controlled_rollout import controlled_rollout_enabled, touch_rollout_state

            if controlled_rollout_enabled():
                touch_rollout_state(ctx.settings.runtime_state_dir)
        except Exception as exc:
            log_event(logger, "controlled_rollout.heartbeat_failed", error=repr(exc)[:200])
        try:
            from app.ops.live_rollback import enforce_live_rollback_if_enabled

            enforce_live_rollback_if_enabled(ctx.settings.runtime_state_dir)
        except Exception as exc:
            log_event(logger, "live_rollback.heartbeat_failed", error=repr(exc)[:200])
        if __import__("app.observability.prepublic_qa", fromlist=["prepublic_qa_enabled"]).prepublic_qa_enabled():
            try:
                from app.observability.prepublic_qa import write_prepublic_validation_report
                from pathlib import Path as _Path
                from utils.database_url import sqlite_path_from_url

                dbp = sqlite_path_from_url(ctx.settings.database_url)
                write_prepublic_validation_report(
                    db_path=_Path(dbp) if dbp else None,
                    runtime_dir=_Path(ctx.settings.runtime_state_dir),
                    log_path=_Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
                )
            except Exception as exc:
                log_event(logger, "prepublic_qa.report_failed", error=repr(exc)[:200])
        ic = run_sqlite_integrity_check(ctx.settings)
        if not ic.get("ok", True):
            from ops.operator_notifications import enqueue_operator_notification

            enqueue_operator_notification(
                ctx.settings.runtime_state_dir,
                kind="sqlite_integrity",
                severity="critical",
                message=f"SQLite integrity failed: {ic.get('integrity') or ic.get('error')}",
                fields=ic,
            )
    except Exception as exc:
        logger.warning("reliability_heartbeat skipped: %s", exc)
    try:
        from ops.economics.tick import run_economics_tick

        run_economics_tick(ctx.settings, logger=logger)
    except Exception as exc:
        logger.warning("economics_tick skipped: %s", exc)
    try:
        from ops.trust.tick import run_trust_tick

        run_trust_tick(ctx.settings, logger=logger)
    except Exception as exc:
        logger.warning("trust_tick skipped: %s", exc)
    log_pipeline_metrics(logger)
    try:
        from app.ops.control_plane.auto_controller import evaluate_auto_ops

        result = evaluate_auto_ops(ctx.settings)
        if result.get("applied"):
            log_event(logger, "ops.auto_controller", **result)
    except Exception as exc:
        logger.warning("ops auto_controller skipped: %s", exc)
    try:
        from app.ops.control_plane import ops_control_snapshot

        log_event(logger, "metrics.ops_control_plane", **ops_control_snapshot())
    except Exception:
        pass


async def run_operational_report(ctx: PipelineContext) -> None:
    from ops.soak_report import log_soak_operational_summary

    log_operational_summary(logger, ctx.settings)
    log_soak_operational_summary(ctx.settings)


async def run_pipeline_tick(ctx: PipelineContext, *, wall_clock_start: float) -> None:
    """
    Single pipeline orchestration tick (collect → summarize → retention → maintenance → metrics).
    Must run under ``get_pipeline_lock()`` from :func:`run_pipeline` for production.
    Exposed for controlled integration tests.
    """
    settings = ctx.settings
    ctx.tick_in_progress = True
    ctx.tick_timings.clear()
    ctx.duplicate_skipped_this_tick = False
    from app.runtime_activity import record_scheduler_tick
    from app.runtime_lifecycle import emit_lifecycle, lifecycle_span_ms

    from ops.runtime_timeline import record_timeline

    from app.operational_mode import load_operational_mode, scheduler_allowed

    op_mode = load_operational_mode(settings.runtime_state_dir, settings)
    if not scheduler_allowed(op_mode):
        log_event(logger, "scheduler.tick.skipped", reason="operational_mode", mode=op_mode.value)
        logger.warning(
            "scheduler tick skipped: operational_mode=%s (set RUNTIME_OPERATIONAL_MODE=production)",
            op_mode.value,
        )
        record_timeline("scheduler.tick.skipped", mode=op_mode.value)
        return

    from app.ops.control_plane.guards import emergency_halt_active, pipeline_tick_allowed
    from app.ops.runtime.pipeline_gate import require_processing_or_skip

    if not require_processing_or_skip(component="pipeline_tick"):
        record_timeline("scheduler.tick.skipped", reason="pipeline_gate")
        return

    if emergency_halt_active():
        log_event(logger, "scheduler.tick.skipped", reason="ops_emergency_halt")
        logger.warning("scheduler tick skipped: OPS emergency_halt active")
        record_timeline("scheduler.tick.skipped", reason="emergency_halt")
        return

    allowed, throttle_reason = pipeline_tick_allowed(base_interval_minutes=settings.pipeline_interval_minutes)
    if not allowed:
        log_event(logger, "scheduler.tick.skipped", reason=throttle_reason)
        logger.info("scheduler tick throttled: %s", throttle_reason)
        record_timeline("scheduler.tick.skipped", reason=throttle_reason)
        return

    from app.state.pipeline_execution_wrapper import execute_pipeline_step

    ctx.tick_collect_rows = 0
    ctx.tick_summarize_idle_reason = ""
    ctx.tick_draft_id = None
    ctx.tick_publish_outcome = "not_reached"
    ctx.is_breaking_stream = False
    ctx.tick_failures = 0

    from utils.operational_context import current_tick_id

    tick_id = current_tick_id() or "unknown"
    from utils.operational_context import get_operational_log_fields

    corr = str(get_operational_log_fields().get("correlation_id") or tick_id)
    await __import__(
        "app.reliability.pipeline_ticks", fromlist=["begin_persisted_tick"]
    ).begin_persisted_tick(tick_id=tick_id, correlation_id=corr)

    record_scheduler_tick()
    record_timeline("scheduler.tick.started", soak_test=settings.soak_test)
    try:
        from app.pipeline.breaking_lane import drain_breaking_lane, should_preempt_normal

        if should_preempt_normal():

            async def _breaking_hook(_payload: dict) -> None:
                log_event(logger, "breaking.lane.item", article_id=_payload.get("article_id"))

            await drain_breaking_lane(_breaking_hook, runtime_dir=settings.runtime_state_dir)
    except Exception as exc:
        log_event(logger, "breaking.lane.drain_failed", error=repr(exc)[:200])
    tick_t0 = time.perf_counter()
    emit_lifecycle("scheduler.tick.started", soak_test=settings.soak_test)
    log_event(logger, "scheduler.pipeline_tick", phase="start", soak_test=settings.soak_test)
    logger.info(
        "pipeline tick running: collect → summarize → publish (soak_test=%s dry_run=%s)",
        settings.soak_test,
        settings.dry_run,
    )
    try:
        await execute_pipeline_step(ctx, "collect", lambda: _collect_step(ctx), require_should_execute=False)
        await _summarize_step(ctx)
        await _scheduled_publish_step(ctx)
        db_before = db_file_size_bytes(settings)
        ret_sec, del_raw, del_drafts = await _retention_step(settings)
        ctx.tick_timings["retention_sec"] = ret_sec
        db_after = db_file_size_bytes(settings)
        log_retention_db_effect(
            logger,
            db_bytes_before=db_before,
            db_bytes_after=db_after,
            deleted_raw=del_raw,
            deleted_drafts=del_drafts,
        )
        t_m = time.perf_counter()
        await maybe_run_sqlite_maintenance(settings)
        ctx.tick_timings["sqlite_maintenance_sec"] = time.perf_counter() - t_m
    except asyncio.CancelledError:
        log_event(logger, "scheduler.pipeline_cancelled", recovery="re_raise")
        raise
    except Exception as exc:
        from app.reliability.terminal_state_resolver import apply_forced_reject_idle
        from app.runtime_watchdog import note_pipeline_exception

        note_pipeline_exception()
        ctx.tick_failures = int(getattr(ctx, "tick_failures", 0) or 0) + 1
        if not (ctx.tick_summarize_idle_reason or "").strip():
            apply_forced_reject_idle(ctx, f"pipeline_inner:{type(exc).__name__}")
        logger.exception("Pipeline inner tick failed: %s", exc)
        ce = classify_runtime_error(exc)
        log_event(
            logger,
            "scheduler.pipeline_tick_failed",
            error=repr(exc),
            recovery="continue_next_tick",
            error_category=ce.category,
            error_code=ce.code,
            severity=ce.severity,
            retryable=ce.retryable,
        )
        append_runtime_event(
            "pipeline_inner_failed",
            message=repr(exc),
            category=ce.category,
            code=ce.code,
            severity=ce.severity,
            retryable=ce.retryable,
        )
        try_save_runtime_snapshot(settings, "pipeline_inner_failed")

    from app.ops.control_plane.state import get_ops_store

    get_ops_store().note_pipeline_tick(unix=time.time())

    ctx.last_scheduler_wall_sec = time.perf_counter() - wall_clock_start
    record_pipeline_duration(ctx.last_scheduler_wall_sec)
    observe_histogram("scheduler_cycle_duration_seconds", ctx.last_scheduler_wall_sec)
    record_pipeline_wall_sample(ctx.last_scheduler_wall_sec)
    if (c := ctx.tick_timings.get("collect_sec")) is not None:
        record_collect_duration(c)
    if (o := ctx.tick_timings.get("openai_sec")) is not None:
        record_openai_duration(o)

    try:
        from ops.economics.resource_accounting import record_resource

        record_resource(
            settings.runtime_state_dir,
            stage="scheduler",
            duration_sec=ctx.last_scheduler_wall_sec,
            count=1,
        )
        if (sc := ctx.tick_timings.get("scoring_sec")) is not None:
            record_resource(settings.runtime_state_dir, stage="scoring", duration_sec=sc, count=1)
        if (pub := ctx.tick_timings.get("scheduled_publish_sec")) is not None:
            record_resource(settings.runtime_state_dir, stage="publish", duration_sec=pub, count=1)
    except Exception:
        pass

    log_event(
        logger,
        "pipeline.timings",
        total_sec=round(ctx.last_scheduler_wall_sec, 4),
        phases=_round_timings(ctx.tick_timings),
    )
    if settings.soak_test:
        rss = rss_bytes_best_effort()
        log_event(
            logger,
            "soak.pipeline_tick_memory",
            rss_bytes=rss,
            asyncio_tasks=len(asyncio.all_tasks(asyncio.get_running_loop())),
            wall_sec=round(ctx.last_scheduler_wall_sec, 3),
        )

    check_tick_anomalies(
        logger,
        settings,
        wall_sec=ctx.last_scheduler_wall_sec,
        cluster_size=ctx.last_cluster_size,
        asyncio_tasks=len(asyncio.all_tasks(asyncio.get_running_loop())),
        rss_bytes=rss_bytes_best_effort(),
    )
    check_phase_trends_after_tick(
        logger,
        settings,
        ctx.tick_timings,
        wall_sec=ctx.last_scheduler_wall_sec,
    )

    record_timeline(
        "scheduler.tick.completed",
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
        soak_test=settings.soak_test,
    )
    emit_lifecycle(
        "scheduler.tick.completed",
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
        event_duration_ms=lifecycle_span_ms(tick_t0),
        soak_test=settings.soak_test,
    )
    log_event(
        logger,
        "scheduler.pipeline_tick",
        phase="end",
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
        soak_test=settings.soak_test,
    )
    logger.info(
        "pipeline tick completed: collect_rows=%s cluster_size=%s summarize_idle=%s draft_id=%s publish=%s wall_sec=%.2f",
        ctx.tick_collect_rows,
        ctx.last_cluster_size,
        ctx.tick_summarize_idle_reason or "none",
        ctx.tick_draft_id,
        ctx.tick_publish_outcome,
        ctx.last_scheduler_wall_sec,
    )
    log_event(
        logger,
        "pipeline.tick.summary",
        collect_rows=ctx.tick_collect_rows,
        cluster_size=ctx.last_cluster_size,
        summarize_idle=ctx.tick_summarize_idle_reason or "",
        draft_id=ctx.tick_draft_id,
        publish_outcome=ctx.tick_publish_outcome,
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
    )
    from app.reliability.tick_finalizer import finalize_pipeline_tick

    await finalize_pipeline_tick(ctx, settings)
    try:
        from app.editorial.burnin_governance import check_output_starvation

        check_output_starvation(ctx.settings)
    except Exception:
        pass
    log_pipeline_metrics(logger)
    _emit_tick_metrics = True
    try:
        from app.observability.runtime_protection import analytics_suppressed

        _emit_tick_metrics = not analytics_suppressed(settings.runtime_state_dir)
    except Exception:
        pass
    if _emit_tick_metrics:
        try:
            from app.editorial.desk_filter import desk_metrics_snapshot

            log_event(logger, "metrics.desk_filter", **desk_metrics_snapshot())
        except Exception:
            pass
        try:
            from app.observability.metrics import lane_metrics_snapshot

            log_event(logger, "metrics.lane_queues", **lane_metrics_snapshot())
        except Exception:
            pass
        try:
            from app.observability.editorial_metrics import editorial_ranking_snapshot

            log_event(logger, "metrics.editorial_ranking", **editorial_ranking_snapshot())
        except Exception:
            pass
        try:
            from app.observability.ops_metrics import ops_snapshot

            log_event(logger, "metrics.ops_lanes", **ops_snapshot())
        except Exception:
            pass
        try:
            from app.ops.control_plane import ops_control_snapshot

            log_event(logger, "metrics.ops_control_plane", **ops_control_snapshot())
        except Exception:
            pass
        try:
            from app.observability.ledger_metrics import ledger_snapshot

            log_event(logger, "metrics.event_ledger", **ledger_snapshot())
        except Exception:
            pass
    if not ctx.duplicate_skipped_this_tick:
        reset_duplicate_skip_streak()
    append_runtime_event(
        "pipeline_tick_completed",
        message="ok",
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
        soak_test=settings.soak_test,
    )
    maybe_flush_runtime_events_to_snapshot(settings)
    try:
        from app.observability.staging_alerts import log_staging_alerts

        log_staging_alerts()
    except Exception:
        pass
    try:
        from app.reliability.checkpoint import persist_tick_checkpoint
        from utils.operational_context import current_tick_id

        persist_tick_checkpoint(
            settings,
            tick_id=current_tick_id() or "unknown",
            publish_outcome=ctx.tick_publish_outcome,
            draft_id=ctx.tick_draft_id,
        )
        from app.observability.event_buffer import get_event_buffer

        get_event_buffer(settings.runtime_state_dir).flush(force=False)
    except Exception as exc:
        log_event(logger, "scheduler.checkpoint_persist_failed", error=repr(exc)[:200])


async def run_pipeline(ctx: PipelineContext) -> None:
    lock = get_pipeline_lock()
    settings = ctx.settings
    t_wall0 = time.perf_counter()
    _tid, _tick_tok, _corr_tok = begin_pipeline_tick()
    append_runtime_event("pipeline_begin", message="run_pipeline", soak_test=settings.soak_test)
    try:
        async with lock:
            await run_pipeline_tick(ctx, wall_clock_start=t_wall0)
    except Exception as exc:
        logger.exception("Pipeline lock or outer failure: %s", exc)
        ce = classify_runtime_error(exc)
        try:
            from app.runtime_watchdog import note_pipeline_exception

            note_pipeline_exception()
        except Exception:
            pass
        log_event(
            logger,
            "scheduler.pipeline_outer_failed",
            error=repr(exc),
            recovery="logged",
            error_category=ce.category,
            error_code=ce.code,
            severity=ce.severity,
            retryable=ce.retryable,
        )
        append_runtime_event(
            "pipeline_outer_failed",
            message=repr(exc),
            category=ce.category,
            code=ce.code,
            severity=ce.severity,
            retryable=ce.retryable,
        )
        try_save_runtime_snapshot(settings, "pipeline_outer_failed")
    finally:
        reset_tick_id(_tick_tok)
        reset_correlation_id(_corr_tok)
        ctx.tick_in_progress = False


async def run_pipeline_wrapped(ctx: PipelineContext) -> None:
    """APScheduler entrypoint: wall-clock tick duration (includes lock wait)."""
    logger.info("pipeline execution started (scheduler job newsroom_pipeline)")
    log_event(
        logger,
        "scheduler.job.invoked",
        job_id="newsroom_pipeline",
        interval_min=ctx.settings.pipeline_interval_minutes,
    )
    t0 = time.perf_counter()
    err: str | None = None
    try:
        await run_pipeline(ctx)
    except BaseException as exc:
        err = repr(exc)
        raise
    finally:
        outer = time.perf_counter() - t0
        log_event(
            logger,
            "scheduler.tick_wall_sec",
            wall_sec=round(outer, 4),
            soak_test=ctx.settings.soak_test,
        )
        if bool(getattr(ctx.settings, "scheduler_diagnostics_enabled", False)):
            from utils.scheduler_diagnostics import record_scheduler_run

            record_scheduler_run(
                "newsroom_pipeline",
                wall_sec=outer,
                error=err,
                expected_interval_sec=float(ctx.settings.pipeline_interval_minutes) * 60.0,
            )
            try:
                from utils.scheduler_diagnostics import scheduler_diagnostics_snapshot

                snap = scheduler_diagnostics_snapshot()
                jobs = snap.get("jobs") or {}
                pipe = jobs.get("newsroom_pipeline") or {}
                lag = pipe.get("max_lag_sec")
                if lag is not None:
                    from app.observability.runtime_health import record_scheduler_lag_ms

                    record_scheduler_lag_ms(float(lag) * 1000.0)
            except Exception:
                pass
