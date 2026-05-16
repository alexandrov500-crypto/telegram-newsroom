"""Registry-based job dispatch (transport-agnostic)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from worker.job_queue import JobEnvelope

from workers.types import ErrorClass, JobType, StructuredJobError

logger = logging.getLogger(__name__)

HandlerFn = Callable[["HandlerContext", JobEnvelope], Awaitable[None]]


@dataclass(slots=True)
class HandlerContext:
    settings: Any
    worker_role: str
    worker_instance_id: str
    bot: Any | None = None
    openai: Any | None = None


class JobHandler(Protocol):
    job_type: JobType

    async def run(self, ctx: HandlerContext, job: JobEnvelope) -> None: ...


class HandlerRegistry:
    def __init__(self) -> None:
        self._by_type: dict[JobType, JobHandler] = {}

    def register(self, handler: JobHandler) -> None:
        if handler.job_type in self._by_type:
            raise ValueError(f"duplicate handler for {handler.job_type}")
        self._by_type[handler.job_type] = handler

    def register_fn(self, jt: JobType, fn: HandlerFn) -> None:
        class _FnHandler:
            job_type = jt

            def __init__(self, f: HandlerFn) -> None:
                self._f = f

            async def run(self, ctx: HandlerContext, job: JobEnvelope) -> None:
                await self._f(ctx, job)

        self.register(_FnHandler(fn))

    def get(self, job_type: JobType) -> JobHandler | None:
        return self._by_type.get(job_type)

    async def dispatch(self, ctx: HandlerContext, job: JobEnvelope) -> None:
        raw = (job.payload or {}).get("job_type")
        if not raw:
            raise StructuredJobError("missing payload.job_type", classification=ErrorClass.PERMANENT)
        try:
            jt = JobType(str(raw))
        except ValueError as exc:
            raise StructuredJobError(f"unknown job_type {raw!r}", classification=ErrorClass.PERMANENT) from exc

        h = self._by_type.get(jt)
        if h is None:
            raise StructuredJobError(f"no handler for {jt.value}", classification=ErrorClass.PERMANENT)
        await h.run(ctx, job)
