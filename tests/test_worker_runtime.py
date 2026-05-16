from __future__ import annotations

import asyncio

import pytest

from tests.conftest import minimal_test_settings
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import close_reliable_transport, init_reliable_transport
from workers.base import WorkerRole
from workers.dispatcher import HandlerContext, HandlerRegistry
from workers.runtime import WorkerRuntime
from workers.types import JobType, StructuredJobError


def test_runtime_shutdown_stops_loop_quickly() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_poll_interval_sec=0.1, worker_max_concurrency=1)
        await init_reliable_transport(s)
        try:
            reg = HandlerRegistry()
            reg.register_fn(JobType.INGEST_ARTICLE, lambda ctx, job: None)
            rt = WorkerRuntime(s, role=WorkerRole.INGEST, job_kind=JobKind.INGEST, registry=reg)
            rt.request_shutdown()
            await rt.run_forever()
        finally:
            await close_reliable_transport()

    asyncio.run(body())


def test_dispatch_unknown_job_type_raises() -> None:
    async def body() -> None:
        s = minimal_test_settings()
        reg = HandlerRegistry()
        reg.register_fn(JobType.INGEST_ARTICLE, lambda ctx, job: None)
        ctx = HandlerContext(settings=s, worker_role="ingest", worker_instance_id="t")
        env = JobEnvelope(JobKind.INGEST, {"job_type": "NOT_A_REAL_TYPE"}, retry=JobRetryMeta())
        with pytest.raises(StructuredJobError):
            await reg.dispatch(ctx, env)

    asyncio.run(body())
