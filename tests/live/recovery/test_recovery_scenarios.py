"""Recovery semantics under simulated outage (CI-safe)."""

from __future__ import annotations

import asyncio

from tests.chaos.framework import RecordingRetryTransport
from tests.conftest import minimal_test_settings
from tests.live.harness import LiveValidationRun, run_bounded
from workers.base import WorkerRole
from workers.dispatcher import HandlerRegistry
from workers.retry import build_policy_from_settings
from workers.runtime import WorkerRuntime
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta


def test_worker_safe_retry_after_simulated_restart() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=True, openai_json_max_retries=1)
        rt = WorkerRuntime(s, role=WorkerRole.INGEST, job_kind=JobKind.INGEST, registry=HandlerRegistry())
        transport = RecordingRetryTransport()
        env = JobEnvelope(JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0))
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "live-recovery-1",
            RuntimeError("transient"),
            0,
            policy,
        )
        assert transport.order == ["enqueue", "ack"]

    asyncio.run(body())


def test_publish_rate_limiter_reset_between_runs() -> None:
    from publisher.rate_limit import get_publish_rate_limiter, reset_publish_rate_limiter_for_tests

    reset_publish_rate_limiter_for_tests()
    t = {"now": 0.0}

    def clock() -> float:
        return t["now"]

    lim = get_publish_rate_limiter(
        min_interval_sec=0.0,
        burst_window_sec=10.0,
        burst_max_messages=1,
        clock=clock,
    )

    async def acquire() -> None:
        await lim.acquire_before_publish(1)

    asyncio.run(acquire())
    reset_publish_rate_limiter_for_tests()
    t["now"] = 0.0
    asyncio.run(acquire())


def test_harness_bounded_timeout_ok() -> None:
    run = LiveValidationRun()

    async def quick() -> str:
        return "ok"

    run.samples.append(run_bounded(quick, name="quick_op", timeout_sec=2.0))
    assert run.ok
    assert run.summary()["sample_count"] == 1
