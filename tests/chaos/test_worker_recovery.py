"""Worker crash / retry recovery chaos validation."""

from __future__ import annotations

import asyncio

import pytest

from tests.chaos.framework import CRASH_SCENARIOS, ChaosTimeline, RecordingRetryTransport
from tests.conftest import minimal_test_settings
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from workers.base import WorkerRole
from workers.dispatcher import HandlerRegistry
from workers.retry import build_policy_from_settings
from workers.runtime import WorkerRuntime
from workers.types import ErrorClass, StructuredJobError


def _runtime(s: object) -> WorkerRuntime:
    return WorkerRuntime(
        s,
        role=WorkerRole.INGEST,
        job_kind=JobKind.INGEST,
        registry=HandlerRegistry(),
    )


@pytest.mark.parametrize("scenario", CRASH_SCENARIOS, ids=lambda s: s.name)
def test_worker_crash_scenario_documented(scenario: object) -> None:
    assert scenario.name


def test_retry_order_legacy_ack_before_enqueue() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=False, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0)
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-chaos-1",
            RuntimeError("chaos transient"),
            0,
            policy,
        )
        assert transport.order == ["ack", "enqueue"]

    asyncio.run(body())


def test_retry_order_safe_enqueue_before_ack() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=True, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0)
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-chaos-2",
            RuntimeError("chaos transient"),
            0,
            policy,
        )
        assert transport.order == ["enqueue", "ack"]

    asyncio.run(body())


def test_enqueue_failure_after_ack_legacy_unsafe() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=False, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport(fail_enqueue=True)
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0)
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        with pytest.raises(RuntimeError, match="enqueue_failed"):
            await rt._handle_failure(
                transport,
                "{}",
                env,
                "d-chaos-3",
                RuntimeError("chaos transient"),
                0,
                policy,
            )
        assert transport.order == ["ack"]

    asyncio.run(body())


def test_bounded_retry_exhausts_to_dlq() -> None:
    async def body() -> None:
        s = minimal_test_settings(openai_json_max_retries=0, worker_retry_deadline_sec=3600.0)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=99)
        )
        policy = build_policy_from_settings(s, envelope_attempt=99)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-chaos-4",
            RuntimeError("chaos transient"),
            99,
            policy,
        )
        assert transport.order == ["dlq"]

    asyncio.run(body())


def test_permanent_error_skips_retry() -> None:
    async def body() -> None:
        s = minimal_test_settings()
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0)
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-chaos-5",
            StructuredJobError("permanent", classification=ErrorClass.PERMANENT),
            0,
            policy,
        )
        assert transport.order == ["dlq"]

    asyncio.run(body())


def test_retry_trace_recorded() -> None:
    from utils.reliability_diagnostics import (
        reset_reliability_diagnostics_for_tests,
        retry_traces_snapshot,
    )

    reset_reliability_diagnostics_for_tests()

    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=True, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta(attempt=0)
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-chaos-6",
            RuntimeError("chaos transient"),
            0,
            policy,
        )

    asyncio.run(body())
    traces = retry_traces_snapshot()
    assert any(t.get("safe_order") is True for t in traces)


def test_stale_recovery_at_least_once() -> None:
    from worker.reliable_transport import InMemoryReliableTransport

    timeline = ChaosTimeline()

    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        await rt.enqueue(
            JobEnvelope(JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta())
        )
        lease = await rt.lease_dequeue(
            JobKind.INGEST, shutdown=shutdown, visibility_sec=0.05, poll_timeout_sec=0.2
        )
        timeline.record("leased", delivery=lease is not None)
        await asyncio.sleep(0.12)
        n = await rt.recover_stale(JobKind.INGEST, visibility_sec=0.05)
        timeline.record("recovered", count=n)
        lease2 = await rt.lease_dequeue(
            JobKind.INGEST, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0
        )
        timeline.record("re_delivered", ok=lease2 is not None)

    asyncio.run(body())
    assert "recovered" in timeline.phases()
    assert timeline.events[-1].get("ok") is True
