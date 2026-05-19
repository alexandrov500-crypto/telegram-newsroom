from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from bot.events.envelope import EventEnvelope
from bot.workflows.checkpoint_store import WorkflowCheckpointStore
from bot.workflows.types import WorkflowCheckpoint, WorkflowRun, WorkflowType

logger = logging.getLogger(__name__)

StepFn = Callable[[WorkflowRun, dict[str, Any]], Awaitable[dict[str, Any]]]


class WorkflowOrchestrator:
    """Checkpointed multi-step workflow execution."""

    def __init__(
        self,
        store: WorkflowCheckpointStore,
        *,
        node_id: str,
        event_sink: Callable[[EventEnvelope], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._node_id = node_id
        self._event_sink = event_sink

    async def run(
        self,
        workflow_type: WorkflowType | str,
        *,
        correlation_id: str,
        steps: list[tuple[str, StepFn]],
        initial: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wtype = workflow_type.value if isinstance(workflow_type, WorkflowType) else workflow_type
        run = WorkflowRun(
            workflow_id=WorkflowRun.new_id(wtype),
            workflow_type=wtype,
            correlation_id=correlation_id,
            status="running",
            holder_node_id=self._node_id,
        )
        if not self._store.start_run(run):
            raise RuntimeError(f"workflow lease not acquired: {run.workflow_id}")

        state = dict(initial or {})
        seq = 0
        try:
            for step_name, step_fn in steps:
                existing = self._store.get_checkpoint(run.workflow_id, step_name)
                if existing is not None:
                    state.update(existing.data)
                    logger.info(
                        "event=workflow_checkpoint_resume workflow_id=%s step=%s",
                        run.workflow_id,
                        step_name,
                    )
                else:
                    state = await step_fn(run, state)
                    seq += 1
                    self._store.save_checkpoint(
                        WorkflowCheckpoint(
                            workflow_id=run.workflow_id,
                            step_name=step_name,
                            data=state,
                            sequence_num=seq,
                        ),
                    )
                self._store.renew_lease(run.workflow_id, node_id=self._node_id)
                if self._event_sink is not None:
                    await self._event_sink(
                        EventEnvelope(
                            event_type="WorkflowCheckpoint",
                            payload={
                                "workflow_id": run.workflow_id,
                                "step": step_name,
                                "correlation_id": correlation_id,
                            },
                            correlation_id=correlation_id,
                            node_id=self._node_id,
                        ),
                    )
            self._store.complete(run.workflow_id)
            return state
        except Exception:
            self._store.fail(run.workflow_id)
            logger.exception("event=workflow_failed workflow_id=%s", run.workflow_id)
            raise
