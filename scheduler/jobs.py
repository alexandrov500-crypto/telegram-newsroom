from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import timedelta

from aiogram import Bot
from openai import AsyncOpenAI

from ai.editorial import compose_post_with_headline
from ai.preprocess import truncate_raw_posts_for_openai
from ai.quality_score import compute_quality_scores
from ai.summary_quality import observe_draft_quality
from ai.summarizer import SummarizerError, summarize_cluster
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
    fetch_unprocessed_raw_posts,
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
from utils.operational_context import begin_pipeline_tick, reset_tick_id
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


async def _collect_step(ctx: PipelineContext) -> None:
    if not ctx.collector_enabled:
        log_event(logger, "collector.skipped", reason="telethon_degraded")
        return
    from app.runtime_lifecycle import emit_lifecycle, lifecycle_span_ms

    settings = ctx.settings
    inserted_total = 0
    t0 = time.perf_counter()
    emit_lifecycle("collector.batch.started", channel_count=len(settings.source_channels))
    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            log_event(logger, "collector.telethon_unauthorized")
            return
        async with session_scope() as session:
            inserted_total = await collect_all_channels(
                client,
                session,
                channels=settings.source_channels,
                limit_per_channel=settings.collect_messages_per_channel,
                telethon_max_attempts=settings.telethon_op_max_attempts,
                channel_delay_seconds=settings.channel_collect_delay_seconds,
            )
        inc("posts_collected", inserted_total)
        if inserted_total > 0:
            from app.runtime_activity import record_collect_success

            record_collect_success(new_rows=inserted_total)
        log_event(
            logger,
            "collector.pipeline_inserted_total",
            new_rows=inserted_total,
            channel_count=len(settings.source_channels),
        )
    except Exception as exc:
        logger.exception("Collection failed: %s", exc)
        log_event(logger, "collector.pipeline_failed", error=repr(exc))
    finally:
        if client.is_connected():
            await client.disconnect()
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
    from app.openai_circuit import get_openai_circuit
    from ops.economics.budgets import allow_ai_request
    from ops.economics.economic_mode import load_economic_mode
    from ops.economics.load_shedding import should_skip_summarize_for_pressure

    settings = ctx.settings
    rd = settings.runtime_state_dir
    econ = load_economic_mode(rd).value
    shed_skip, shed_reason = should_skip_summarize_for_pressure(settings, rd, priority_level="medium")
    if shed_skip:
        log_event(logger, "scheduler.summarize_skipped", reason=shed_reason, stage="load_shedding")
        return
    ai_ok, ai_reason = allow_ai_request(rd, priority_level="medium", economic_mode=econ)
    if not ai_ok:
        log_event(logger, "scheduler.summarize_skipped", reason=ai_reason, stage="ai_budget")
        return

    if not ctx.ai_pipeline_enabled or not get_openai_circuit().allow_request():
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason="openai_degraded",
            stage="startup",
            circuit_state=get_openai_circuit().state().value,
        )
        return
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
        log_event(logger, "scheduler.summarize_skipped", reason="no_unprocessed_posts", stage="fetch_posts")
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
    ctx.last_cluster_size = len(cluster)

    if len(cluster) < settings.min_raw_posts_for_ai:
        log_event(
            logger,
            "scheduler.summarize_skipped",
            reason="cluster_below_min_posts",
            cluster_size=len(cluster),
            min_required=settings.min_raw_posts_for_ai,
            stage="precluster",
        )
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return

    combined_text = "\n".join((p.text or "")[:2000] for p in cluster)
    fp = compute_event_fingerprint(cluster)
    history = load_event_history(settings.runtime_state_dir)
    evo = classify_event_evolution(fp, combined_text=combined_text, history=history)
    identity = build_event_identity(cluster)
    ents = extract_entities(combined_text)
    record_entity_cooccurrence(settings.runtime_state_dir, ents)

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
    rank_clusters(
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
    policy_matches, gov_suppress, gov_reason = evaluate_policies(
        cluster,
        runtime_dir=settings.runtime_state_dir,
        topic_key=identity.topic_hint,
        dominant_channel=dom_ch,
        fingerprint=fp,
    )
    div_blocked, div_codes = apply_cooldowns(
        settings.runtime_state_dir,
        topic_key=identity.topic_hint,
        channels=[str(p.channel_name or "") for p in cluster],
    )
    if ranking_trace.hard_block or gov_suppress or div_blocked:
        reasons = list(ranking_trace.reason_codes) + div_codes
        if gov_reason:
            reasons.append(gov_reason)
        append_decision(
            runtime_dir=settings.runtime_state_dir,
            decision_type="cluster_governance_suppress",
            outcome="suppressed",
            subject_id=fp,
            reason_codes=reasons[:24],
            ranking_trace=ranking_trace.to_dict(),
            policy_matches=policy_matches,
        )
        record_suppression_ttl(settings.runtime_state_dir, fp, 1800.0, reason=gov_reason or reasons[0] if reasons else "")
        record_suppression_metric(settings.runtime_state_dir, gov_reason or "governance")
        inc("skipped_intelligence_suppress")
        log_event(logger, "scheduler.cluster_suppressed", reasons=reasons, stage="governance")
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
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
    if pipeline_decision.defer_to_next_tick:
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
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
    if pipeline_decision.suppress:
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
        ctx.tick_timings["cluster_sec"] = time.perf_counter() - t_cl
        return
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
    try:
        sc = await summarize_cluster(
            openai,
            settings=settings,
            model=settings.openai_model,
            posts=cluster,
            max_json_retries=settings.openai_json_max_retries,
            request_timeout_sec=settings.openai_request_timeout_sec,
            log_chat_latency=True,
        )
        post_text, used_ids, headline = sc.post_text, sc.used_ids, sc.headline
        _ai_exec_patch = sc.execution.to_draft_extras_patch()
    except SummarizerError as exc:
        circuit = get_openai_circuit()
        circuit.record_failure(str(exc))
        try:
            from ops.incidents.triggers import note_openai_failure

            note_openai_failure(settings, reason=str(exc))
        except Exception:
            pass
        log_event(logger, "openai.summarize_failed", error=str(exc), recovery="aborted_draft")
        ctx.tick_timings["openai_sec"] = time.perf_counter() - t_ai
        observe_histogram("summarize_duration_seconds", ctx.tick_timings["openai_sec"])
        return
    ctx.tick_timings["openai_sec"] = time.perf_counter() - t_ai
    observe_histogram("summarize_duration_seconds", ctx.tick_timings["openai_sec"])
    from app.runtime_activity import record_ai_success

    record_ai_success()

    if not used_ids or not post_text:
        log_event(logger, "scheduler.summarize_skipped", reason="model_empty_or_no_ids", stage="post_openai")
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
        log_event(logger, "scheduler.summarize_skipped", reason="empty_after_source_dedupe", stage="post_openai")
        return

    draft_body = compose_post_with_headline(settings, post_text, headline)
    content_hash = sha256_hex(draft_body)

    used_posts = [id_to_post[i] for i in used_ids]
    sources_payload: list[dict[str, object]] = [
        {
            "channel": p.channel_name,
            "message_id": p.message_id,
        }
        for p in used_posts
    ]

    keys = {(str(p.channel_name).strip(), int(p.message_id)) for p in used_posts}
    raw_post_ids_for_db = sorted(
        {
            p.id
            for p in cluster
            if (str(p.channel_name).strip(), int(p.message_id)) in keys
        }
    )

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

    t_dbw = time.perf_counter()
    editorial_intel: dict[str, object] | None = None
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
        if skip:
            inc("skipped_duplicates")
            ctx.duplicate_skipped_this_tick = True
            record_duplicate_skip(logger, settings)
            log_event(logger, "draft.skipped_duplicate", reason=reason, hash_prefix=content_hash[:12])
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
            ctx.tick_timings["db_draft_sec"] = time.perf_counter() - t_dbw
            return

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
        await merge_draft_extras(session, draft_id, _ai_exec_patch)
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
        gate_block, gate_reasons = evaluate_publish_gate(
            settings,
            settings.runtime_state_dir,
            pol_eff,
            topic_key=topic_dedupe_key(identity.topic_hint),
            is_breaking=bool(brk.get("is_breaking")),
        )
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

    inc("drafts_generated")
    log_event(
        logger,
        "draft.created",
        draft_id=draft_id,
        raw_posts_used=len(raw_post_ids_for_db),
        content_hash_prefix=content_hash[:12],
    )

    t_no = time.perf_counter()
    try:
        sources_display = json.dumps(sources_payload, ensure_ascii=False, indent=2)
        await notify_admin_new_draft(
            bot,
            settings,
            draft_id=draft_id,
            content=draft_body,
            sources=sources_display,
            editorial_intelligence=editorial_intel if isinstance(editorial_intel, dict) else None,
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


async def _scheduled_publish_step(ctx: PipelineContext) -> None:
    t0 = time.perf_counter()
    settings = ctx.settings
    ctx.tick_timings["scheduled_publish_sec"] = 0.0
    if settings.dry_run:
        return
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    bot = ctx.bot
    async with session_scope() as session:
        ids = await list_due_scheduled_draft_ids(session, limit=3)
    for did in ids:
        res = await execute_admin_publication_flow(bot, settings, did)
        if res.outcome is PublishFlowOutcome.OK:
            inc("scheduled_publish_fired")
            append_runtime_event("scheduled_publish_ok", message="published", draft_id=did)
        elif res.outcome is PublishFlowOutcome.SEND_FAILED:
            append_runtime_event(
                "scheduled_publish_failed",
                message=(res.error or "")[:300],
                draft_id=did,
            )
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
        from ops.economics.tick import run_economics_tick

        run_economics_tick(ctx.settings, logger=logger)
    except Exception as exc:
        logger.warning("economics_tick skipped: %s", exc)
    log_pipeline_metrics(logger)


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
        record_timeline("scheduler.tick.skipped", mode=op_mode.value)
        return

    record_scheduler_tick()
    record_timeline("scheduler.tick.started", soak_test=settings.soak_test)
    tick_t0 = time.perf_counter()
    emit_lifecycle("scheduler.tick.started", soak_test=settings.soak_test)
    log_event(logger, "scheduler.pipeline_tick", phase="start", soak_test=settings.soak_test)
    try:
        await _collect_step(ctx)
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
        from app.runtime_watchdog import note_pipeline_exception

        note_pipeline_exception()
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
    log_pipeline_metrics(logger)
    if not ctx.duplicate_skipped_this_tick:
        reset_duplicate_skip_streak()
    append_runtime_event(
        "pipeline_tick_completed",
        message="ok",
        wall_sec=round(ctx.last_scheduler_wall_sec, 4),
        soak_test=settings.soak_test,
    )
    maybe_flush_runtime_events_to_snapshot(settings)


async def run_pipeline(ctx: PipelineContext) -> None:
    lock = get_pipeline_lock()
    settings = ctx.settings
    t_wall0 = time.perf_counter()
    _, _tick_tok = begin_pipeline_tick()
    append_runtime_event("pipeline_begin", message="run_pipeline", soak_test=settings.soak_test)
    try:
        async with lock:
            await run_pipeline_tick(ctx, wall_clock_start=t_wall0)
    except Exception as exc:
        logger.exception("Pipeline lock or outer failure: %s", exc)
        ce = classify_runtime_error(exc)
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
        ctx.tick_in_progress = False


async def run_pipeline_wrapped(ctx: PipelineContext) -> None:
    """APScheduler entrypoint: wall-clock tick duration (includes lock wait)."""
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
