from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot.editorial.multilingual_publish import (
    languages_to_publish,
    publish_to_language_channel,
    resolve_localized_publish_text,
)
from bot.publisher import ChannelPublisher
from bot.publishing.channel_router import ChannelRouter
from bot.runtime.state import runtime_state
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.editorial_repository import EditorialRepository, PendingNewsItem
from bot.storage.entity_repository import EntityRepository
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.repository import LinkDedup
from bot.storage.source_repository import SourceRepository

if TYPE_CHECKING:
    from bot.publishing.idempotency import PublishIdempotencyStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishFlowResult:
    success: bool
    message_id: int | None = None
    error: str | None = None


async def publish_pending_item(
    item: PendingNewsItem,
    *,
    publisher: ChannelPublisher,
    editorial: EditorialRepository,
    link_dedup: LinkDedup | None,
    sources: SourceRepository | None,
    entities: EntityRepository | None,
    analytics: AnalyticsRepository | None,
    channel_router: ChannelRouter | None = None,
    localizations: LocalizationRepository | None = None,
    adaptive: object | None = None,
    idempotency: PublishIdempotencyStore | None = None,
    node_id: str = "local",
    operator_approved: bool = False,
    publish_guard: object | None = None,
    misinfo_score: float = 0.0,
    open_contradictions: int = 0,
    publish_confidence: float | None = None,
) -> PublishFlowResult:
    """Publish a pending item to configured language channels. Fail-open; never raises."""
    try:
        from bot.ops_forensics.correlation import bind_publish_context, set_correlation_id
        from bot.ops_forensics.hooks import record_publish_lifecycle

        bind_publish_context(pending_news_id=item.id)
        record_publish_lifecycle("started", pending_news_id=item.id)
    except Exception:
        pass

    from bot.production_safety.context_holder import get_production_safety
    from bot.reliability.context_holder import get_reliability

    from bot.ga_ops.context_holder import get_ga_ops
    from bot.post_ga.context_holder import get_post_ga

    ga = get_ga_ops()
    post_ga = get_post_ga()
    quality_overall = 0.8
    if ga is not None:
        headline = (item.optimized_headline or item.title or "")[:200]
        summary = (item.summary or item.translated_summary or "")[:2000]
        q = ga.validate_quality(
            headline=headline,
            summary=summary,
            story_id=getattr(item, "story_id", None),
            pending_news_id=item.id,
            contradiction_score=open_contradictions / 10.0 if open_contradictions else 0.0,
        )
        if not q.passed:
            logger.warning(
                "event=publish_blocked_ga_quality pending_news_id=%d blockers=%s",
                item.id,
                q.blockers,
            )
            return PublishFlowResult(success=False, error=f"ga_quality:{','.join(q.blockers)}")
        quality_overall = q.overall
        if post_ga is not None:
            post_ga.quality.observe_output(
                headline=headline,
                summary=summary,
                quality_overall=q.overall,
            )

    ps = get_production_safety()
    if ps is not None:
        verdict = await ps.evaluate_publish(
            item=item,
            channel_id=publisher.channel_id,
            operator_approved=operator_approved,
            misinfo_score=misinfo_score,
            open_contradictions=open_contradictions,
            publish_confidence=publish_confidence,
        )
        if not verdict.allowed:
            logger.warning(
                "event=publish_blocked_production_safety pending_news_id=%d %s",
                item.id,
                verdict.reason,
            )
            return PublishFlowResult(success=False, error=verdict.reason)

    rel = get_reliability()
    if rel is not None:
        snap = rel.health.last_snapshot
        if snap is not None:
            gate = rel.publish_gate.evaluate(
                health_state=snap.overall_state,
                health_score=snap.health_score,
                queue_depth=snap.queue_depth,
                cognition_latency_ms=float(
                    next(
                        (
                            float(s.metadata.get("latency_ms", 0))
                            for s in snap.subsystems
                            if s.name.value == "cognition"
                        ),
                        0.0,
                    )
                ),
                telegram_failure_rate=0.0,
                fatal_incidents_recent=rel.incidents.recent_fatal_count(),
                operator_approved=operator_approved,
            )
            if not gate.allowed:
                logger.warning(
                    "event=publish_blocked_gate pending_news_id=%d %s",
                    item.id,
                    gate.reason,
                )
                return PublishFlowResult(success=False, error=gate.reason)
            if ga is not None:
                trust = publish_confidence if publish_confidence is not None else 0.85
                narrative_key = (item.link or item.title or "")[:64]
                pub_langs = languages_to_publish(item) or [item.source_language]
                tg = ga.check_publish(
                    queue_depth=snap.queue_depth,
                    trust_score=trust,
                    narrative_key=narrative_key,
                    language=pub_langs[0],
                )
                if not tg.allowed:
                    logger.warning(
                        "event=publish_blocked_ga_traffic pending_news_id=%d %s",
                        item.id,
                        tg.reason,
                    )
                    return PublishFlowResult(success=False, error=f"ga_traffic:{tg.reason}")

    from bot.live_deploy.context_holder import get_live_deploy

    live_deploy = get_live_deploy()
    if (
        live_deploy is not None
        and live_deploy.settings.enabled
        and not runtime_state.shadow_publish_only
        and not runtime_state.staging_mode
    ):
        ld_sig: dict = {}
        try:
            from bot.ops_playbook.context_holder import get_ops_playbook

            pb = get_ops_playbook()
            if pb is not None and pb._signals_fn:
                ld_sig = pb._signals_fn()
        except Exception:
            pass
        if rel is not None and rel.health.last_snapshot:
            ld_sig["slo_burn"] = max(0.0, 1.0 - rel.health.last_snapshot.health_score)
            ld_sig["retry_amplification"] = rel.health.last_snapshot.health_score < 0.5
        lv = live_deploy.publication_guard.evaluate(
            pending_news_id=item.id,
            quality_score=quality_overall,
            trust_score=publish_confidence if publish_confidence is not None else 0.85,
            publish_confidence=publish_confidence,
            operator_approved=operator_approved,
            signals=ld_sig,
        )
        if not lv.allowed:
            try:
                from bot.operator_console.context import get_operator_console

                console = get_operator_console()
                if console is not None:
                    await console.send_raw(
                        live_deploy.notify_publication_blocked(
                            pending_news_id=item.id,
                            blockers=lv.blockers,
                        ),
                        category="alert",
                        force=True,
                    )
            except Exception:
                logger.exception("event=live_guard_notify_failed")
            return PublishFlowResult(success=False, error=lv.reason)

    from bot.live_ops.context_holder import get_controlled_live

    controlled = get_controlled_live()
    if (
        controlled is not None
        and controlled.settings.enabled
        and not runtime_state.staging_mode
    ):
        headline = (item.optimized_headline or item.title or "")[:200]
        summary = (item.summary or item.translated_summary or "")[:2000]
        topic = (item.priority_reason or item.source or "general")[:64]
        trust = publish_confidence if publish_confidence is not None else 0.85
        cv = controlled.publish_guard.evaluate(
            pending_news_id=item.id,
            headline=headline,
            summary=summary,
            source=item.source or "",
            topic=topic,
            operator_approved=operator_approved,
            quality_score=quality_overall,
            trust_score=trust,
            channel_id=publisher.channel_id,
            cluster_id=getattr(item, "cluster_id", None),
            tags=list(item.tags or []),
        )
        forensics_cid = None
        try:
            from bot.ops_forensics.correlation import get_correlation_id

            forensics_cid = get_correlation_id()
        except Exception:
            pass
        controlled.record_publish_decision(
            pending_news_id=item.id,
            source=item.source or "",
            cluster_id=getattr(item, "cluster_id", None),
            confidence_score=trust,
            trust_score=trust,
            safety_score=quality_overall,
            guard_result="pass" if cv.allowed else "hold",
            hold_reason=cv.reason if (cv.hold or not cv.allowed) else None,
            operator_override=operator_approved,
            published=False,
            channel_id=publisher.channel_id,
            blockers=list(cv.blockers),
            correlation_id=forensics_cid,
        )
        if cv.hold or not cv.allowed:
            try:
                from bot.editorial.flow_health.funnel import record_funnel

                record_funnel(
                    "QUARANTINED",
                    rejection_reason=cv.blockers[0] if cv.blockers else cv.reason,
                )
            except Exception:
                pass
            controlled.on_publish_failure(pending_news_id=item.id, reason=cv.reason)
            try:
                from bot.live_ops.ops_alerts import notify_ops_channel

                blockers = ", ".join(cv.blockers) or cv.reason
                await notify_ops_channel(
                    f"<b>Live publish hold</b> #{item.id}\n{blockers}",
                    force=True,
                )
            except Exception:
                logger.exception("event=controlled_live_notify_failed")
            return PublishFlowResult(success=False, error=cv.reason)
        if cv.route_shadow:
            runtime_state.shadow_publish_only = True

    if runtime_state.dry_run_mode:
        logger.info("event=publish_skipped dry_run=true pending_news_id=%d", item.id)
        return PublishFlowResult(success=True, message_id=None)

    if runtime_state.staging_mode:
        from bot.staging.safety import StagingSafetyEnforcer

        safety = StagingSafetyEnforcer().evaluate(
            auto_approval=runtime_state.auto_approval_enabled,
            publish_confidence=publish_confidence,
            open_contradictions=open_contradictions,
            misinfo_score=misinfo_score,
            operator_approved=operator_approved,
            staging_mode=True,
        )
        if not safety.allowed:
            logger.warning(
                "event=publish_blocked_staging pending_news_id=%d reason=%s",
                item.id,
                safety.blocked_reason,
            )
            if publish_guard is not None:
                publish_guard.record_audit(
                    pending_news_id=item.id,
                    channel_id=publisher.channel_id,
                    correlation_id="blocked",
                    approved=False,
                    detail={"reason": safety.blocked_reason, "warnings": list(safety.warnings)},
                )
            return PublishFlowResult(success=False, error=safety.blocked_reason or "staging_blocked")

    router = channel_router
    if router is None and not publisher.channel_configured:
        return PublishFlowResult(success=False, error="channel_not_configured")

    linked_entities: list[str] = []
    if entities is not None:
        try:
            linked_entities = entities.get_entity_names_for_pending(item.id)
        except Exception:
            logger.exception("event=publish_flow_entities_failed id=%d", item.id)

    langs = languages_to_publish(item)
    if not langs:
        langs = [item.source_language]

    primary_message_id: int | None = None
    any_success = False
    last_error: str | None = None

    from bot.observability.loop_diagnostics import publishing_active

    correlation_id = "local"
    if publish_guard is not None:
        verdict = publish_guard.evaluate_channel(
            router.channel_for(langs[0]) if router else publisher.channel_id
        )
        correlation_id = verdict.correlation_id
        try:
            from bot.ops_forensics.correlation import set_correlation_id

            set_correlation_id(correlation_id)
        except Exception:
            pass
        if not verdict.allowed:
            return PublishFlowResult(success=False, error=verdict.reason)

    with publishing_active():
        for lang in langs:
            channel_id = None
            if router is not None:
                channel_id = router.channel_for(lang)
            elif publisher.channel_configured:
                channel_id = publisher.channel_id

            if publish_guard is not None:
                ch_verdict = publish_guard.evaluate_channel(channel_id)
                if not ch_verdict.allowed:
                    return PublishFlowResult(success=False, error=ch_verdict.reason)
                correlation_id = ch_verdict.correlation_id
                try:
                    from bot.ops_forensics.correlation import set_correlation_id

                    set_correlation_id(correlation_id)
                except Exception:
                    pass

            idem_key: str | None = None
            if idempotency is not None:
                idem_key = idempotency.build_key(
                    pending_news_id=item.id,
                    channel_id=channel_id,
                    language=lang,
                    content_hash=item.link,
                )
                existing = idempotency.try_begin(
                    idem_key,
                    pending_news_id=item.id,
                    digest_id=None,
                    channel_id=channel_id,
                    language=lang,
                    node_id=node_id,
                )
                if existing is not None:
                    if existing.status == "completed" and existing.telegram_message_id:
                        try:
                            from bot.observability.metrics import record_publish_dedup

                            record_publish_dedup("completed_receipt")
                        except Exception:
                            pass
                        any_success = True
                        if primary_message_id is None:
                            primary_message_id = existing.telegram_message_id
                        continue
                    if existing.status == "in_progress":
                        try:
                            from bot.observability.metrics import record_publish_dedup

                            record_publish_dedup("in_progress")
                        except Exception:
                            pass
                        return PublishFlowResult(
                            success=False,
                            error="publish_in_progress",
                        )

            text = resolve_localized_publish_text(item, lang, localizations)
            result = await publish_to_language_channel(
                item,
                lang,
                publisher=publisher,
                router=router,
                localizations=localizations,
                trending_entities=linked_entities,
            )
            if not result.success:
                last_error = result.error
                if idempotency is not None and idem_key is not None:
                    idempotency.fail(idem_key, allow_retry=True)
                if publish_guard is not None and getattr(publish_guard, "_repo", None):
                    from bot.publishing.telegram_reliability import (
                        DeliveryAudit,
                        TelegramDeliveryReliability,
                    )

                    TelegramDeliveryReliability(publish_guard._repo).record_delivery(
                        DeliveryAudit(
                            message_key=f"pub_{item.id}_{lang}",
                            channel_id=channel_id or 0,
                            success=False,
                            latency_ms=result.duration_ms,
                            error=result.error,
                        )
                    )
                continue
            any_success = True
            if ga is not None:
                ga.traffic.record_publish(
                    language=lang,
                    narrative_key=(item.link or item.title or "")[:64],
                )
            if post_ga is not None:
                post_ga.calibration.record_publish(channel_id=channel_id, engagement=0.55)
                post_ga.analytics.record_publish(
                    success=True,
                    latency_sec=result.duration_ms / 1000.0 if result.duration_ms else 0.0,
                    quality=quality_overall,
                )
            if publish_guard is not None and getattr(publish_guard, "_repo", None):
                from bot.publishing.telegram_reliability import (
                    DeliveryAudit,
                    TelegramDeliveryReliability,
                )

                TelegramDeliveryReliability(publish_guard._repo).record_delivery(
                    DeliveryAudit(
                        message_key=f"pub_{item.id}_{lang}",
                        channel_id=channel_id or 0,
                        success=True,
                        latency_ms=result.duration_ms,
                        message_id=result.message_id,
                    )
                )
            if primary_message_id is None:
                primary_message_id = result.message_id
            if idempotency is not None and idem_key is not None and result.message_id is not None:
                idempotency.complete(idem_key, telegram_message_id=result.message_id)

            if analytics is not None and result.message_id is not None:
                try:
                    source_trust = 0.5
                    if sources is not None and item.source:
                        source_trust = sources.get_profile(item.source).trust_score
                    analytics.record_published_post(
                        telegram_message_id=result.message_id,
                        pending_news_id=item.id,
                        cluster_id=item.cluster_id,
                        headline=text.headline,
                        hook_line=text.hook,
                        entities=linked_entities,
                        topics=item.tags,
                        priority_score=item.priority_score,
                        source_trust=source_trust,
                        language=lang,
                    )
                except Exception:
                    logger.exception(
                        "event=publish_flow_analytics_failed id=%d lang=%s",
                        item.id,
                        lang,
                    )

    if not any_success:
        cl = get_controlled_live()
        if cl is not None:
            cl.on_publish_failure(
                pending_news_id=item.id,
                reason=last_error or "publish_failed",
            )
        return PublishFlowResult(success=False, error=last_error or "publish_failed")

    if not editorial.mark_published(item.id):
        return PublishFlowResult(
            success=False,
            error="mark_published_failed",
            message_id=primary_message_id,
        )

    if rel is not None:
        rel.publish_gate.record_publish()
    if ps is not None and publisher.channel_id is not None:
        await ps.record_publish_success(story_id=item.id, channel_id=publisher.channel_id)

    if sources is not None and item.source:
        try:
            sources.record_approval(item.source)
        except Exception:
            logger.exception("event=publish_flow_source_record_failed")

    if link_dedup is not None:
        try:
            link_dedup.mark_seen(item.link)
        except Exception:
            logger.exception("event=publish_flow_dedup_failed link=%r", item.link)

    runtime_state.published_count += 1
    try:
        from bot.editorial.flow_health.funnel import record_funnel

        record_funnel("PUBLISHED")
        try:
            from bot.editorial.flow_health.digest_discipline import note_normal_publish

            note_normal_publish()
        except Exception:
            pass
        try:
            from bot.editorial.flow_health.duplicate_escape import record_publish_forensics

            record_publish_forensics(
                pending_news_id=item.id,
                headline=(item.optimized_headline or item.title or "")[:300],
                cluster_id=getattr(item, "cluster_id", None),
                source=item.source,
                tags=list(item.tags or []),
                published=True,
            )
        except Exception:
            pass
        if operator_approved:
            record_funnel("APPROVED")
    except Exception:
        pass
    if publish_guard is not None:
        publish_guard.record_audit(
            pending_news_id=item.id,
            channel_id=channel_id,
            correlation_id=correlation_id,
            approved=True,
            detail={"operator_approved": operator_approved, "shadow": runtime_state.shadow_publish_only},
        )
        try:
            from bot.observability.metrics import record_staging_shadow_publish

            record_staging_shadow_publish()
        except Exception:
            pass
    if adaptive is not None:
        try:
            adaptive.control_plane.feedback.record_publish_outcome(  # type: ignore[attr-defined]
                pending_news_id=item.id,
                story_id=item.cluster_id,
                source=item.source,
                priority_score=item.priority_score,
                engagement_proxy=min(1.0, item.priority_score + 0.1),
            )
        except Exception:
            logger.exception("event=adaptive_publish_outcome_failed id=%d", item.id)

    if (
        live_deploy is not None
        and not runtime_state.shadow_publish_only
        and not runtime_state.staging_mode
    ):
        try:
            from bot.operator_console.context import get_operator_console

            console = get_operator_console()
            if console is not None:

                async def _first_pub_notify(t: str) -> None:
                    await console.send_raw(t, category="digest", force=True)

                await live_deploy.maybe_send_report(
                    "first_publication",
                    notify=_first_pub_notify,
                )
        except Exception:
            logger.exception("event=first_publication_report_failed")

    defer_analytics = False
    if any_success:
        langs = languages_to_publish(item)
        primary_lang = langs[0] if langs else "en"
        pub_text = resolve_localized_publish_text(item, primary_lang, localizations)
        defer_analytics = False
        try:
            from bot.ops_resilience.context import should_defer_analytics

            defer_analytics = should_defer_analytics()
        except Exception:
            pass
        if defer_analytics:
            logger.debug("event=post_publish_analytics_deferred id=%d", item.id)
        else:
            try:
                from bot.editorial.quality.service import schedule_publish_quality_record

                schedule_publish_quality_record(
                    pending_news_id=item.id,
                    headline=pub_text.headline,
                    summary=pub_text.summary or "",
                    link=item.link,
                    tags=list(item.tags or []),
                    source=item.source,
                    hook_line=pub_text.hook,
                )
            except Exception:
                logger.debug("event=editorial_quality_schedule_skipped id=%d", item.id)

            try:
                from bot.editorial.priority.service import (
                    evaluate_item_priority,
                    schedule_priority_record,
                )

                pri = evaluate_item_priority(item)
                schedule_priority_record(pending_news_id=item.id, result=pri)
            except Exception:
                logger.debug("event=editorial_priority_schedule_skipped id=%d", item.id)

            try:
                from bot.editorial.memory.service import schedule_storyline_record

                schedule_storyline_record(
                    pending_news_id=item.id,
                    headline=pub_text.headline,
                    summary=pub_text.summary or "",
                    tags=list(item.tags or []),
                    source=item.source,
                    cluster_id=item.cluster_id,
                )
            except Exception:
                logger.debug("event=editorial_memory_schedule_skipped id=%d", item.id)

    if controlled is not None:
        controlled.on_publish_success(pending_news_id=item.id)
        try:
            from bot.editorial.flow_health.floor import floor_allows_relaxed_publish

            pub_text_headline = (item.optimized_headline or item.title or "")[:200]
            floor_allows_relaxed_publish(headline=pub_text_headline)
        except Exception:
            pass
        if not defer_analytics:
            try:
                from bot.trust_calibration.service import schedule_publish_trust_record

                schedule_publish_trust_record(item.id)
            except Exception:
                logger.debug("event=trust_calibration_schedule_skipped id=%d", item.id)
        try:
            from bot.live_ops.bridge import emit_publish_delivered
            from bot.live_ops.context_holder import get_live_ops

            lo = get_live_ops()
            if lo is not None and primary_message_id and publisher.channel_id:
                await emit_publish_delivered(
                    lo,
                    pending_news_id=item.id,
                    channel_id=publisher.channel_id,
                    message_id=primary_message_id,
                    correlation_id=correlation_id,
                )
        except Exception:
            logger.exception("event=controlled_live_emit_failed")

    return PublishFlowResult(success=True, message_id=primary_message_id)
