from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

from bot.workflows.checkpoint_store import WorkflowCheckpointStore
from bot.workflows.types import WorkflowRun, WorkflowStatus

logger = logging.getLogger(__name__)

CompensationHook = Callable[[WorkflowRun], Awaitable[None]]


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    POISON = "poison"
    PARTITION = "partition"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryPlan:
    workflow_id: str
    failure_class: FailureClass
    action: str
    retry_delay_sec: float
    partial_replay: bool
    cancel: bool
    reason: str


class IntelligentRecoveryService:
    """Topology-aware recovery with retry classification."""

    def __init__(
        self,
        store: WorkflowCheckpointStore,
        *,
        node_id: str,
        policy_doc: Any | None = None,
    ) -> None:
        self._store = store
        self._node_id = node_id
        self._policy_doc = policy_doc
        self._compensation: dict[str, CompensationHook] = {}
        self._failure_counts: dict[str, int] = {}
        self._topology: Any | None = None
        self._redis_healthy = True
        self._telegram_rate_limited = False

    def set_health_signals(
        self,
        *,
        topology: Any | None = None,
        redis_healthy: bool = True,
        telegram_rate_limited: bool = False,
    ) -> None:
        self._topology = topology
        self._redis_healthy = redis_healthy
        self._telegram_rate_limited = telegram_rate_limited

    def register_compensation(self, workflow_type: str, hook: CompensationHook) -> None:
        self._compensation[workflow_type] = hook

    def classify_error(self, error: str | None) -> FailureClass:
        if not error:
            return FailureClass.UNKNOWN
        text = error.lower()
        permanent = ["invalid_token", "forbidden", "chat_not_found", "policy_deny"]
        if self._policy_doc is not None:
            permanent = list(
                self._policy_doc.retry_escalation.get("permanent_error_patterns", permanent),
            )
        for pat in permanent:
            if pat.lower() in text:
                return FailureClass.PERMANENT
        if "rate limit" in text or "flood" in text or self._telegram_rate_limited:
            return FailureClass.RATE_LIMIT
        if not self._redis_healthy or "redis" in text or "connection" in text:
            return FailureClass.TRANSIENT
        if "partition" in text or "region" in text:
            return FailureClass.PARTITION
        if "timeout" in text or "temporary" in text:
            return FailureClass.TRANSIENT
        return FailureClass.UNKNOWN

    def plan_recovery(self, run: WorkflowRun, *, error: str | None = None) -> RecoveryPlan:
        fc = self.classify_error(error)
        wid = run.workflow_id
        self._failure_counts[wid] = self._failure_counts.get(wid, 0) + 1
        count = self._failure_counts[wid]
        base = 2.0
        max_delay = 120.0
        max_retries = 5
        if self._policy_doc is not None:
            esc = self._policy_doc.retry_escalation
            base = float(esc.get("base_delay_sec", 2.0))
            max_delay = float(esc.get("max_delay_sec", 120.0))
            max_retries = int(esc.get("max_transient_retries", 5))

        if fc == FailureClass.PERMANENT:
            return RecoveryPlan(wid, fc, "quarantine", 0, False, True, "permanent error")
        if count >= max_retries:
            return RecoveryPlan(wid, FailureClass.POISON, "isolate", 0, False, True, "max retries")
        delay = min(max_delay, base * (2 ** (count - 1)))
        partial = fc in (FailureClass.TRANSIENT, FailureClass.RATE_LIMIT)
        if fc == FailureClass.RATE_LIMIT:
            delay = max(delay, 30.0)
        return RecoveryPlan(
            wid,
            fc,
            "retry_with_backoff",
            delay,
            partial,
            False,
            f"{fc.value} attempt {count}",
        )

    async def recover_stalled(self, *, stale_sec: int = 600) -> int:
        recovered = 0
        for run in self._store.list_stalled(stale_sec=stale_sec):
            plan = self.plan_recovery(run)
            if plan.cancel:
                self._store.fail(run.workflow_id)
                continue
            if await self._execute_plan(run, plan):
                recovered += 1
        return recovered

    async def recover_orphans(self) -> int:
        recovered = 0
        for run in self._store.list_orphaned_leases():
            plan = self.plan_recovery(run, error="orphan lease")
            if await self._execute_plan(run, plan):
                recovered += 1
        return recovered

    async def _execute_plan(self, run: WorkflowRun, plan: RecoveryPlan) -> bool:
        if plan.cancel:
            self._store.fail(run.workflow_id)
            return False
        new_run = WorkflowRun(
            workflow_id=run.workflow_id,
            workflow_type=run.workflow_type,
            correlation_id=run.correlation_id,
            status=WorkflowStatus.RECOVERING.value,
            holder_node_id=self._node_id,
        )
        if not self._store.start_run(new_run):
            return False
        hook = self._compensation.get(run.workflow_type)
        if hook is not None:
            try:
                await hook(run)
            except Exception as exc:
                logger.exception("event=intelligent_recovery_hook_failed")
                self.plan_recovery(run, error=repr(exc))
        try:
            from bot.observability.metrics import record_workflow_recovery

            record_workflow_recovery(run.workflow_type)
        except Exception:
            pass
        return True

    def resume_from_checkpoint(self, workflow_id: str, step_name: str) -> dict | None:
        cp = self._store.get_checkpoint(workflow_id, step_name)
        return cp.data if cp else None

    def analyze_stuck_graph(self) -> list[dict]:
        """Return stuck workflow summary for operations layer."""
        stalled = self._store.list_stalled(stale_sec=300)
        return [
            {
                "workflow_id": r.workflow_id,
                "type": r.workflow_type,
                "holder": r.holder_node_id,
                "failures": self._failure_counts.get(r.workflow_id, 0),
            }
            for r in stalled
        ]
