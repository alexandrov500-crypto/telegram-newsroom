from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from bot.editorial.agents import (
    RiskAssessment,
    StoryAgentContext,
    breaking_headline_prefix,
    evaluate_story_risk,
    should_auto_approve,
    should_trigger_breaking_alert,
)
from bot.editorial.publish_flow import publish_pending_item
from bot.publisher import ChannelPublisher
from bot.runtime.state import runtime_state
from bot.storage.agent_repository import (
    ACTION_AUTO_APPROVED,
    ACTION_BREAKING_ALERT,
    ACTION_HUMAN_REVIEW,
    ACTION_RISK_ASSESSED,
    AgentRepository,
)
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.entity_repository import EntityRepository
from bot.publishing.channel_router import ChannelRouter
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.repository import LinkDedup
from bot.storage.source_repository import SourceRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentProcessResult:
    pending_news_id: int
    assessment: RiskAssessment | None
    auto_approved: bool = False
    breaking_alert: bool = False
    published: bool = False


class EditorialAgentService:
    """Bounded autonomous editorial decisions after enqueue."""

    def __init__(
        self,
        agent_repo: AgentRepository,
        editorial: EditorialRepository,
        publisher: ChannelPublisher,
        clusters: ClusterRepository | None = None,
        sources: SourceRepository | None = None,
        entities: EntityRepository | None = None,
        analytics: AnalyticsRepository | None = None,
        link_dedup: LinkDedup | None = None,
        channel_router: ChannelRouter | None = None,
        localizations: LocalizationRepository | None = None,
    ) -> None:
        self._agents = agent_repo
        self._editorial = editorial
        self._publisher = publisher
        self._clusters = clusters
        self._sources = sources
        self._entities = entities
        self._analytics = analytics
        self._link_dedup = link_dedup
        self._channel_router = channel_router
        self._localizations = localizations

    def _build_context(self, item) -> StoryAgentContext:
        entity_names: list[str] = []
        if self._entities is not None:
            entity_names = self._entities.get_entity_names_for_pending(item.id)

        source_trust = 0.5
        source_approval_ratio = 0.5
        if self._sources is not None and item.source:
            profile = self._sources.get_profile(item.source)
            source_trust = profile.trust_score
            source_approval_ratio = profile.approval_ratio
            reversal_penalty = self._agents.adaptive_penalty_from_reversals(item.source)
            source_trust = max(0.05, source_trust - reversal_penalty)

        variant_count = item.variant_count
        if self._clusters is not None and item.cluster_id is not None:
            view = self._clusters.get_cluster_view(item.cluster_id)
            variant_count = max(variant_count, view.variant_count)

        topic_virality = 0.5
        if self._analytics is not None:
            topic_virality = self._analytics.topic_virality(item.tags)

        return StoryAgentContext(
            pending_news_id=item.id,
            title=item.title,
            summary=item.summary,
            tags=item.tags,
            source=item.source,
            source_count=max(item.source_count, variant_count),
            priority_score=item.priority_score,
            source_trust=source_trust,
            source_approval_ratio=source_approval_ratio,
            entity_names=entity_names,
            cluster_variant_count=variant_count,
            topic_virality=topic_virality,
        )

    async def evaluate_pending(self, pending_news_id: int) -> RiskAssessment | None:
        item = self._editorial.get_by_id(pending_news_id)
        if item is None:
            return None
        try:
            ctx = self._build_context(item)
            assessment = evaluate_story_risk(ctx)
            self._agents.save_risk_assessment(pending_news_id, assessment)
            self._agents.record_action(
                pending_news_id=pending_news_id,
                action_type=ACTION_RISK_ASSESSED,
                decision={
                    "risk_score": assessment.risk_score,
                    "confidence": assessment.publish_confidence,
                    "factors": list(assessment.risk_factors),
                    "blocked": list(assessment.blocked_categories),
                },
                reversible=False,
            )
            if assessment.requires_human_review:
                self._agents.record_action(
                    pending_news_id=pending_news_id,
                    action_type=ACTION_HUMAN_REVIEW,
                    decision={"reason": "risk_threshold"},
                    reversible=False,
                )
            return assessment
        except Exception:
            logger.exception(
                "event=agent_action_failed action=evaluate pending_news_id=%d",
                pending_news_id,
            )
            return None

    async def process_new_pending(self, pending_news_id: int) -> AgentProcessResult:
        """Evaluate risk, optionally auto-approve and publish. Never raises."""
        assessment = await self.evaluate_pending(pending_news_id)
        if assessment is None:
            return AgentProcessResult(pending_news_id=pending_news_id, assessment=None)

        item = self._editorial.get_by_id(pending_news_id)
        if item is None or item.status != "pending":
            return AgentProcessResult(pending_news_id=pending_news_id, assessment=assessment)

        ctx = self._build_context(item)
        breaking = should_trigger_breaking_alert(ctx, assessment)
        if breaking:
            self._agents.record_action(
                pending_news_id=pending_news_id,
                action_type=ACTION_BREAKING_ALERT,
                decision={"priority": ctx.priority_score, "sources": ctx.source_count},
                reversible=False,
            )

        await _notify_operator_cognitive(
            pending_news_id=pending_news_id,
            item=item,
            assessment=assessment,
            ctx=ctx,
        )

        auto_enabled = runtime_state.auto_approval_enabled
        if not should_auto_approve(ctx, assessment, auto_approval_enabled=auto_enabled):
            return AgentProcessResult(
                pending_news_id=pending_news_id,
                assessment=assessment,
                breaking_alert=breaking,
            )

        publish_item = item
        if breaking:
            prefixed = f"{breaking_headline_prefix()}: {item.title}"
            publish_item = replace(item, title=prefixed[:240])

        self._agents.record_action(
            pending_news_id=pending_news_id,
            action_type=ACTION_AUTO_APPROVED,
            decision={
                "risk_score": assessment.risk_score,
                "confidence": assessment.publish_confidence,
                "breaking": breaking,
            },
            reversible=True,
        )
        logger.info(
            "event=auto_approved_story pending_news_id=%d risk=%.3f confidence=%.3f",
            pending_news_id,
            assessment.risk_score,
            assessment.publish_confidence,
        )

        flow = await publish_pending_item(
            publish_item,
            publisher=self._publisher,
            editorial=self._editorial,
            link_dedup=self._link_dedup,
            sources=self._sources,
            entities=self._entities,
            analytics=self._analytics,
            channel_router=self._channel_router,
            localizations=self._localizations,
        )
        if not flow.success:
            self._agents.reverse_latest_auto_approval(pending_news_id)
            logger.warning(
                "event=auto_approved_story publish_failed pending_news_id=%d error=%r",
                pending_news_id,
                flow.error,
            )
            return AgentProcessResult(
                pending_news_id=pending_news_id,
                assessment=assessment,
                breaking_alert=breaking,
            )

        return AgentProcessResult(
            pending_news_id=pending_news_id,
            assessment=assessment,
            auto_approved=True,
            breaking_alert=breaking,
            published=True,
        )


async def _notify_operator_cognitive(
    *,
    pending_news_id: int,
    item,
    assessment,
    ctx: StoryAgentContext,
) -> None:
    try:
        from bot.cognitive.integrations import route_for_operation
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            return
        route = route_for_operation(
            "editorial_review",
            importance_score=item.priority_score,
        )
        if route is None:
            return
        warnings: list[str] = []
        if assessment.requires_human_review:
            warnings.append("human review required")
        if assessment.risk_score > 0.6:
            warnings.append("elevated risk")
        await console.notify_cognitive_route(
            news_id=pending_news_id,
            route_decision=route,
            priority=item.priority_score,
            contradiction_count=0,
            trust_signal=ctx.source_trust,
            epistemic_warnings=warnings,
        )
    except Exception:
        logger.debug("event=operator_cognitive_notify_skipped", exc_info=True)
