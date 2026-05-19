from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from bot.policy.evaluator import PolicyContext
from bot.policy.runtime import PolicyRuntime
from bot.policy.types import WorkflowQoSClass
from bot.storage.coordination_repository import CoordinationRepository

logger = logging.getLogger(__name__)


@dataclass
class LoadSignals:
    queue_backlog: int = 0
    stream_lag_sec: float = 0.0
    dlq_count: int = 0
    workflow_stalled: int = 0
    pending_stream: int = 0
    publish_throughput: float = 0.0
    replay_backlog: int = 0
    region_health: dict[str, float] = field(default_factory=dict)

    @property
    def pressure_score(self) -> float:
        """0=idle, 1=critical overload."""
        parts = [
            min(1.0, self.queue_backlog / 500.0),
            min(1.0, self.stream_lag_sec / 60.0),
            min(1.0, self.dlq_count / 100.0),
            min(1.0, self.workflow_stalled / 10.0),
            min(1.0, self.pending_stream / 200.0),
        ]
        return max(parts)


@dataclass
class ScheduleDecision:
    job_name: str
    acquired: bool
    qos_class: str
    lease_ttl_sec: int
    reason: str


class AdaptiveScheduler:
    """Load-aware scheduler with QoS-weighted global leases."""

    def __init__(
        self,
        repo: CoordinationRepository,
        *,
        node_id: str,
        policy: PolicyRuntime | None = None,
    ) -> None:
        self._repo = repo
        self._node_id = node_id
        self._policy = policy
        self._signals = LoadSignals()
        self._concurrency_limit = 8
        self._active_jobs = 0
        self._shed_classes: set[str] = set()

    def update_signals(self, signals: LoadSignals) -> None:
        self._signals = signals
        pressure = signals.pressure_score
        throttle = 8
        if self._policy is not None:
            throttle = int(
                self._policy.evaluator.document.workflow_throttle.get(
                    "max_concurrent_per_node",
                    8,
                ),
            )
        self._concurrency_limit = max(1, int(throttle * (1.0 - pressure * 0.6)))
        self._shed_classes = set()
        backlog = signals.queue_backlog
        if self._policy is not None:
            shed_at = int(
                self._policy.evaluator.document.workflow_throttle.get(
                    "shed_analytics_above_backlog",
                    300,
                ),
            )
            if backlog >= shed_at:
                self._shed_classes.add(WorkflowQoSClass.ANALYTICS.value)
                self._shed_classes.add(WorkflowQoSClass.BACKFILL.value)
            if backlog >= shed_at * 1.5:
                self._shed_classes.add(WorkflowQoSClass.FEDERATION.value)
                self._shed_classes.add(WorkflowQoSClass.MEDIA.value)

    def try_schedule(
        self,
        job_name: str,
        *,
        qos_class: str = WorkflowQoSClass.DIGEST.value,
        base_ttl_sec: int = 180,
    ) -> ScheduleDecision:
        if qos_class in self._shed_classes:
            return ScheduleDecision(
                job_name=job_name,
                acquired=False,
                qos_class=qos_class,
                lease_ttl_sec=0,
                reason=f"load shedding active for {qos_class}",
            )
        if self._active_jobs >= self._concurrency_limit:
            return ScheduleDecision(
                job_name=job_name,
                acquired=False,
                qos_class=qos_class,
                lease_ttl_sec=0,
                reason=f"concurrency limit {self._concurrency_limit}",
            )
        if self._policy is not None:
            ctx = PolicyContext(
                node_id=self._node_id,
                queue_backlog=self._signals.queue_backlog,
                stream_lag_sec=self._signals.stream_lag_sec,
                dlq_count=self._signals.dlq_count,
                workflow_stalled=self._signals.workflow_stalled,
                region_health=self._signals.region_health,
                degradation_mode="normal",
                workflow_class=qos_class,
            )
            decision = self._policy.decide("workflow_start", ctx)
            if not decision.allowed:
                return ScheduleDecision(
                    job_name=job_name,
                    acquired=False,
                    qos_class=qos_class,
                    lease_ttl_sec=0,
                    reason=decision.reason,
                )
        weight = 1.0
        if self._policy is not None:
            weight = self._policy.evaluator.lease_weight(qos_class)
        ttl = max(30, int(base_ttl_sec / max(weight, 0.1)))
        acquired = self._repo.try_acquire_job(job_name, node_id=self._node_id, ttl_sec=ttl)
        if acquired:
            self._active_jobs += 1
            logger.info(
                "event=adaptive_job_acquired job=%s qos=%s ttl=%d pressure=%.2f",
                job_name,
                qos_class,
                ttl,
                self._signals.pressure_score,
            )
        return ScheduleDecision(
            job_name=job_name,
            acquired=acquired,
            qos_class=qos_class,
            lease_ttl_sec=ttl,
            reason="lease acquired" if acquired else "lease held elsewhere",
        )

    def release(self, job_name: str) -> bool:
        ok = self._repo.release_job(job_name, node_id=self._node_id)
        if ok and self._active_jobs > 0:
            self._active_jobs -= 1
        return ok
