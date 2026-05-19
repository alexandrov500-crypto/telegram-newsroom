from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from bot.workflows.checkpoint_store import WorkflowCheckpointStore
from bot.workflows.types import WorkflowRun, WorkflowStatus

logger = logging.getLogger(__name__)

CompensationHook = Callable[[WorkflowRun], Awaitable[None]]


class WorkflowRecoveryService:
    """Orphan detection, stall recovery, and retry orchestration."""

    def __init__(self, store: WorkflowCheckpointStore, *, node_id: str) -> None:
        self._store = store
        self._node_id = node_id
        self._compensation: dict[str, CompensationHook] = {}

    def register_compensation(self, workflow_type: str, hook: CompensationHook) -> None:
        self._compensation[workflow_type] = hook

    async def recover_stalled(self, *, stale_sec: int = 600) -> int:
        stalled = self._store.list_stalled(stale_sec=stale_sec)
        recovered = 0
        for run in stalled:
            if await self._try_takeover(run):
                recovered += 1
        return recovered

    async def recover_orphans(self) -> int:
        orphans = self._store.list_orphaned_leases()
        recovered = 0
        for run in orphans:
            if await self._try_takeover(run):
                recovered += 1
        return recovered

    async def _try_takeover(self, run: WorkflowRun) -> bool:
        logger.warning(
            "event=workflow_recovery_attempt workflow_id=%s holder=%s node=%s",
            run.workflow_id,
            run.holder_node_id,
            self._node_id,
        )
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
            except Exception:
                logger.exception(
                    "event=workflow_compensation_failed workflow_id=%s",
                    run.workflow_id,
                )
        try:
            from bot.observability.metrics import record_workflow_recovery

            record_workflow_recovery(run.workflow_type)
        except Exception:
            pass
        return True

    def resume_from_checkpoint(self, workflow_id: str, step_name: str) -> dict[str, Any] | None:
        cp = self._store.get_checkpoint(workflow_id, step_name)
        return cp.data if cp else None
