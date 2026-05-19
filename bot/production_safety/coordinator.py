from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.production_safety.circuit_breakers import CircuitBreakerRegistry
from bot.production_safety.containment import RuntimeContainment
from bot.production_safety.editorial_trust import EditorialTrustEngine, EditorialTrustInput
from bot.production_safety.financial_safety import FinancialSafetyController
from bot.production_safety.forensics import ForensicsStore
from bot.production_safety.operator_failover import OperatorFailoverManager
from bot.production_safety.repository import ProductionSafetyRepository
from bot.production_safety.rollout import RolloutController
from bot.production_safety.security import ProductionSecurityLayer
from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.telegram_delivery import TelegramDeliveryGuard
from bot.production_safety.types import (
    CostMode,
    ProductionSafetySnapshot,
    PublishSafetyVerdict,
    StoryTrustState,
)
from bot.runtime.state import runtime_state
from bot.staging.safety import StagingSafetyEnforcer

logger = logging.getLogger(__name__)


@dataclass
class ProductionSafetyCoordinator:
    """Final hardening facade for production Telegram operation."""

    settings: ProductionSafetySettings
    repository: ProductionSafetyRepository
    telegram: TelegramDeliveryGuard
    financial: FinancialSafetyController
    editorial_trust: EditorialTrustEngine
    containment: RuntimeContainment
    rollout: RolloutController
    breakers: CircuitBreakerRegistry
    forensics: ForensicsStore
    security: ProductionSecurityLayer
    operators: OperatorFailoverManager
    _staging_safety: StagingSafetyEnforcer | None = None

    def __post_init__(self) -> None:
        self._staging_safety = StagingSafetyEnforcer()
        stage = self.settings.rollout_stage
        if self.repository.get_rollout_stage() == "INTERNAL_SHADOW":
            try:
                from bot.production_safety.types import RolloutStage

                self.repository.set_rollout_stage(
                    RolloutStage(stage).value if stage in RolloutStage.__members__ else stage,
                    detail={"init": True},
                )
            except Exception:
                pass

    async def evaluate_publish(
        self,
        *,
        item: Any,
        channel_id: int | None,
        operator_approved: bool = False,
        operator_id: int | None = None,
        admin_ids: frozenset[int] = frozenset(),
        misinfo_score: float = 0.0,
        open_contradictions: int = 0,
        publish_confidence: float | None = None,
        source_count: int = 1,
    ) -> PublishSafetyVerdict:
        blockers: list[str] = []
        warnings: list[str] = []

        if not self.breakers.telegram.allow_request():
            blockers.append("circuit_telegram_open")
        if not self.breakers.openai.allow_request():
            warnings.append("circuit_openai_open")

        fin = self.financial.snapshot()
        if fin.mode == CostMode.EMERGENCY_LOW_COST:
            warnings.append("emergency_low_cost_mode")

        trust = self.editorial_trust.evaluate(
            EditorialTrustInput(
                publish_confidence=publish_confidence,
                source_count=source_count,
                duplicate_narrative=False,
                misinfo_score=misinfo_score,
                hallucination_suspicion=0.0,
                open_contradictions=open_contradictions,
                operator_approved=operator_approved,
                unsafe_content=False,
            ),
        )
        if trust == StoryTrustState.BLOCKED:
            blockers.append(f"trust_{trust.value}")
        elif trust == StoryTrustState.REVIEW_REQUIRED:
            if not operator_approved:
                blockers.append("trust_review_required")

        ok_rollout, rollout_reason = self.rollout.can_publish_now()
        if not ok_rollout:
            blockers.append(rollout_reason)
        if channel_id is not None and not self.rollout.channel_allowed(channel_id):
            blockers.append("channel_not_whitelisted")

        tg = self.telegram.stats()
        if tg.publish_paused and not tg.operator_override:
            blockers.append("telegram_publish_paused")

        if self._staging_safety:
            staging_v = self._staging_safety.evaluate(
                auto_approval=runtime_state.auto_approval_enabled,
                publish_confidence=publish_confidence,
                open_contradictions=open_contradictions,
                misinfo_score=misinfo_score,
                operator_approved=operator_approved,
                staging_mode=runtime_state.staging_mode,
            )
            if not staging_v.allowed:
                blockers.append(staging_v.blocked_reason or "staging_blocked")
            warnings.extend(staging_v.warnings)

        auth_ok, auth_reason = self.security.validate_publish_authorization(
            operator_id=operator_id,
            operator_approved=operator_approved,
            admin_ids=admin_ids,
        )
        if operator_approved and not auth_ok:
            blockers.append(auth_reason)

        from bot.reliability.context_holder import get_reliability

        rel = get_reliability()
        if rel is not None:
            snap = rel.health.last_snapshot
            if snap is not None:
                gate = rel.publish_gate.evaluate(
                    health_state=snap.overall_state,
                    health_score=snap.health_score,
                    queue_depth=snap.queue_depth,
                    cognition_latency_ms=0.0,
                    telegram_failure_rate=1.0 - tg.success_ratio,
                    fatal_incidents_recent=rel.incidents.recent_fatal_count(),
                    operator_approved=operator_approved,
                )
                if not gate.allowed:
                    blockers.append(gate.reason)

        allowed = len(blockers) == 0
        if item is not None and hasattr(item, "id"):
            self.forensics.record(
                story_id=int(item.id),
                trace_type="publish_decision",
                payload={
                    "allowed": allowed,
                    "trust": trust.value,
                    "blockers": blockers,
                    "warnings": warnings,
                },
            )

        return PublishSafetyVerdict(
            allowed=allowed,
            reason=blockers[0] if blockers else "ok",
            trust_state=trust,
            rollout_stage=self.rollout.current_stage(),
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )

    async def tick(
        self,
        *,
        queue_depth: int,
        obs_repo: Any | None = None,
        dlq_depth: int = 0,
        openai_failures: int = 0,
        telegram_failures: int = 0,
    ) -> ProductionSafetySnapshot:
        contain = self.containment.assess(
            queue_depth=queue_depth,
            poison_count=self.repository.poison_count(),
            ingest_paused=runtime_state.ingestion_paused,
        )
        if self.containment.should_pause_ingest(contain):
            runtime_state.ingestion_paused = True
            logger.warning("event=ingest_paused_containment queue=%d", queue_depth)

        fin = self.financial.snapshot(obs_repo=obs_repo)
        if fin.mode == CostMode.EMERGENCY_LOW_COST:
            runtime_state.operational_mode = "cost_emergency"
        elif fin.mode == CostMode.COST_SAVING:
            runtime_state.operational_mode = "cost_saving"

        for _ in range(openai_failures):
            self.breakers.openai.record_failure()
        for _ in range(telegram_failures):
            self.breakers.telegram.record_failure()

        if dlq_depth > 50:
            self.breakers.rss.record_failure()
        else:
            self.breakers.rss.record_success()

        tg = self.telegram.stats()
        publish_allowed, _ = self.rollout.can_publish_now()

        snap = ProductionSafetySnapshot(
            telegram=tg,
            financial=fin,
            containment=contain,
            rollout_stage=self.rollout.current_stage(),
            cost_mode=fin.mode,
            publish_allowed=publish_allowed and not tg.publish_paused,
            metadata={"breakers": self.breakers.snapshot()},
        )

        if self.settings.auto_rollback_on_fatal:
            from bot.reliability.context_holder import get_reliability

            rel = get_reliability()
            if rel is not None and rel.incidents.recent_fatal_count() > 0:
                self.rollout.rollback_to_shadow(reason="fatal_incident_auto")

        return snap

    def record_publish_success(self, *, story_id: int, channel_id: int) -> None:
        self.rollout.record_publish()
        self.breakers.telegram.record_success()
        self.forensics.record(
            story_id=story_id,
            trace_type="publish_success",
            payload={"channel_id": channel_id},
        )
