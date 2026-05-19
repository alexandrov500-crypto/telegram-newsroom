from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.policy.runtime import PolicyRuntime, build_policy_runtime
from bot.runtime.adaptive_scheduler import AdaptiveScheduler, LoadSignals
from bot.runtime.degradation import DegradationStateMachine
from bot.runtime.editorial_qos import EditorialQoS
from bot.runtime.intelligent_recovery import IntelligentRecoveryService
from bot.runtime.operations import OperationalDecisionEngine
from bot.runtime.region import RegionOrchestrator
from bot.runtime.replay_guard import ReplayGuard
from bot.runtime.topology import TopologyIntelligence
from bot.workflows.checkpoint_store import WorkflowCheckpointStore

logger = logging.getLogger(__name__)


@dataclass
class AutonomousRuntime:
    """Self-healing editorial control plane facade."""

    policy: PolicyRuntime
    scheduler: AdaptiveScheduler
    recovery: IntelligentRecoveryService
    degradation: DegradationStateMachine
    topology: TopologyIntelligence
    qos: EditorialQoS
    region: RegionOrchestrator
    replay_guard: ReplayGuard
    operations: OperationalDecisionEngine
    coordination: Any

    async def passive_tick(self, *, queue_backlog: int = 0) -> dict[str, Any]:
        """Pilot canary: monitoring-only tick without recovery or publish pressure."""
        signals = LoadSignals(queue_backlog=queue_backlog)
        snap = self.topology.build_snapshot(
            coordination=self.coordination,
            signals=signals,
            leader=None,
        )
        return {
            "passive": True,
            "health": snap.health_score,
            "pressure": signals.pressure_score,
            "degradation": self.degradation.current().mode,
        }

    async def tick(
        self,
        *,
        node_id: str,
        node_region: str,
        is_leader: bool,
        queue_backlog: int = 0,
        stream_lag_sec: float = 0.0,
        dlq_count: int = 0,
        pending_stream: int = 0,
        workflow_stalled: int = 0,
        apply_operations: bool = False,
        passive: bool = False,
    ) -> dict[str, Any]:
        if passive:
            return await self.passive_tick(queue_backlog=queue_backlog)

        signals = LoadSignals(
            queue_backlog=queue_backlog,
            stream_lag_sec=stream_lag_sec,
            dlq_count=dlq_count,
            pending_stream=pending_stream,
            workflow_stalled=workflow_stalled,
        )
        snap = self.topology.build_snapshot(
            coordination=self.coordination,
            signals=signals,
            leader=self.coordination.current_leader() if is_leader else None,
        )
        signals.region_health = {
            k: float(v.get("score", 0.5)) for k, v in snap.regions.items()
        }
        self.scheduler.update_signals(signals)
        self.recovery.set_health_signals(topology=snap, redis_healthy=dlq_count < 200)
        self.policy.sync_from_cluster()

        deg = self.degradation.current()
        triggers = self.policy.evaluator.document.degradation_triggers
        if signals.pressure_score > 0.9:
            self.degradation.transition(
                "publish_safe",
                reason=f"pressure {signals.pressure_score:.2f}",
            )
        elif signals.pressure_score < 0.5 and deg.mode != "normal" and not deg.operator_override:
            self.degradation.rollback()

        await self.recovery.recover_orphans()
        await self.recovery.recover_stalled()

        ops_report = await self.operations.evaluate_cycle(
            signals=signals,
            is_leader=is_leader,
            apply=apply_operations,
        )
        try:
            from bot.observability.metrics import set_topology_health, set_workflow_stalled

            set_topology_health(snap.health_score)
            set_workflow_stalled(workflow_stalled)
        except Exception:
            pass
        return {
            "health": snap.health_score,
            "degradation": deg.mode,
            "pressure": signals.pressure_score,
            "recommendations": snap.recommendations,
            "operations": ops_report.summary(),
            "starvation": self.qos.starvation_risk(),
        }


def build_autonomous_runtime(
    db_path: Path,
    *,
    node_id: str,
    node_region: str,
    coordination: Any,
    workflow_store: WorkflowCheckpointStore | None = None,
    publish_idempotency: Any | None = None,
) -> AutonomousRuntime:
    policy = build_policy_runtime(db_path, node_id=node_id, coordination=coordination)
    wf_store = workflow_store or WorkflowCheckpointStore(db_path)
    degradation = DegradationStateMachine(db_path)
    topology = TopologyIntelligence(db_path)
    qos = EditorialQoS(db_path)
    region = RegionOrchestrator(node_region=node_region, policy=policy)
    scheduler = AdaptiveScheduler(coordination, node_id=node_id, policy=policy)
    recovery = IntelligentRecoveryService(
        wf_store,
        node_id=node_id,
        policy_doc=policy.evaluator.document,
    )
    replay_guard = ReplayGuard(db_path, publish_idempotency=publish_idempotency)
    operations = OperationalDecisionEngine(
        node_id=node_id,
        policy=policy,
        degradation=degradation,
        topology=topology,
        coordination=coordination,
    )
    return AutonomousRuntime(
        policy=policy,
        scheduler=scheduler,
        recovery=recovery,
        degradation=degradation,
        topology=topology,
        qos=qos,
        region=region,
        replay_guard=replay_guard,
        operations=operations,
        coordination=coordination,
    )
