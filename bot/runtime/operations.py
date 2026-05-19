from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bot.policy.evaluator import PolicyContext
from bot.policy.runtime import PolicyRuntime
from bot.policy.types import DegradationMode
from bot.runtime.degradation import DegradationStateMachine
from bot.runtime.topology import TopologyIntelligence, TopologySnapshot

logger = logging.getLogger(__name__)


@dataclass
class OperationalAction:
    action: str
    target: str
    reason: str
    explain: str
    reversible: bool = True
    applied: bool = False


@dataclass
class OperationsReport:
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    actions: list[OperationalAction] = field(default_factory=list)
    topology_health: float = 1.0

    def summary(self) -> str:
        lines = [f"Operations report @ {self.timestamp}", f"health={self.topology_health:.2f}", ""]
        for a in self.actions:
            flag = "APPLIED" if a.applied else "SUGGESTED"
            lines.append(f"[{flag}] {a.action} {a.target}: {a.explain}")
        return "\n".join(lines)


class OperationalDecisionEngine:
    """Deterministic autonomous operational reasoning."""

    def __init__(
        self,
        *,
        node_id: str,
        policy: PolicyRuntime,
        degradation: DegradationStateMachine,
        topology: TopologyIntelligence,
        coordination: Any,
    ) -> None:
        self._node_id = node_id
        self._policy = policy
        self._degradation = degradation
        self._topology = topology
        self._coordination = coordination
        self._audit: list[OperationalAction] = []

    async def evaluate_cycle(
        self,
        *,
        signals: Any,
        is_leader: bool,
        apply: bool = False,
    ) -> OperationsReport:
        if not is_leader:
            return OperationsReport()
        leader = self._coordination.current_leader()
        snap = self._topology.build_snapshot(
            coordination=self._coordination,
            signals=signals,
            leader=leader,
        )
        report = OperationsReport(topology_health=snap.health_score)
        deg = self._degradation.current()

        triggers = self._policy.evaluator.document.degradation_triggers
        if signals.queue_backlog >= int(triggers.get("queue_backlog", 500)):
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="degrade",
                        target=DegradationMode.PUBLISH_SAFE.value,
                        reason="queue backlog",
                        explain=f"backlog {signals.queue_backlog} exceeds threshold",
                    ),
                    apply,
                ),
            )
        if signals.stream_lag_sec >= float(triggers.get("stream_lag_sec", 30)):
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="slow_replay",
                        target="global",
                        reason="stream lag",
                        explain=f"lag {signals.stream_lag_sec:.1f}s — throttle replay",
                    ),
                    apply,
                ),
            )
        if signals.dlq_count >= int(triggers.get("dlq_count", 100)):
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="quarantine_dlq",
                        target="stream",
                        reason="dlq pressure",
                        explain=f"dlq={signals.dlq_count}",
                    ),
                    apply,
                ),
            )
        for node_id in snap.unhealthy_nodes[:3]:
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="drain_node",
                        target=node_id,
                        reason="unhealthy",
                        explain="node missed heartbeats or unhealthy status",
                    ),
                    apply,
                ),
            )
        for part in snap.hot_partitions[:2]:
            report.actions.append(
                OperationalAction(
                    action="rebalance_partition",
                    target=part,
                    reason="hot partition",
                    explain="high lag or paused — suggest rebalance",
                    applied=False,
                ),
            )
        low_regions = [r for r, b in snap.regions.items() if b.get("score", 1) < 0.35]
        if low_regions and deg.mode == DegradationMode.NORMAL.value:
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="degrade",
                        target=DegradationMode.DEGRADED_FEDERATION.value,
                        reason="regional instability",
                        explain=f"regions degraded: {low_regions}",
                    ),
                    apply,
                ),
            )
        if snap.health_score > 0.85 and deg.mode != DegradationMode.NORMAL.value and not deg.operator_override:
            report.actions.append(
                self._maybe_apply(
                    OperationalAction(
                        action="rollback_degradation",
                        target=deg.mode,
                        reason="health restored",
                        explain="cluster health recovered",
                    ),
                    apply,
                ),
            )
        self._audit.extend(report.actions)
        return report

    def _maybe_apply(self, action: OperationalAction, apply: bool) -> OperationalAction:
        if not apply:
            return action
        if action.action == "degrade":
            self._degradation.transition(action.target, reason=action.reason)
            action.applied = True
        elif action.action == "rollback_degradation":
            self._degradation.rollback()
            action.applied = True
        elif action.action == "drain_node":
            for n in self._coordination.list_nodes(include_stale=True):
                if n.node_id == action.target:
                    self._coordination.set_node_status(
                        node_id=n.node_id,
                        role=n.role,
                        status="draining",
                    )
                    action.applied = True
        return action

    def recent_audits(self, limit: int = 20) -> list[OperationalAction]:
        return self._audit[-limit:]
