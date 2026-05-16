"""Retry ordering invariants (safe vs legacy) — semantics verification."""

from __future__ import annotations

import asyncio

from tests.chaos.framework import RecordingRetryTransport
from tests.conftest import minimal_test_settings
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from workers.base import WorkerRole
from workers.dispatcher import HandlerRegistry
from workers.retry import build_policy_from_settings
from workers.runtime import WorkerRuntime


def _runtime(s: object) -> WorkerRuntime:
    return WorkerRuntime(
        s,
        role=WorkerRole.INGEST,
        job_kind=JobKind.INGEST,
        registry=HandlerRegistry(),
    )


def test_safe_retry_enqueue_before_ack() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=True, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST,
            {"job_type": "INGEST_ARTICLE"},
            retry=JobRetryMeta(attempt=0),
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-sem-safe",
            RuntimeError("transient"),
            0,
            policy,
        )
        assert transport.order == ["enqueue", "ack"]

    asyncio.run(body())


def test_legacy_retry_ack_before_enqueue() -> None:
    async def body() -> None:
        s = minimal_test_settings(worker_retry_safe=False, openai_json_max_retries=1)
        rt = _runtime(s)
        transport = RecordingRetryTransport()
        env = JobEnvelope(
            JobKind.INGEST,
            {"job_type": "INGEST_ARTICLE"},
            retry=JobRetryMeta(attempt=0),
        )
        policy = build_policy_from_settings(s, envelope_attempt=0)
        await rt._handle_failure(
            transport,
            "{}",
            env,
            "d-sem-legacy",
            RuntimeError("transient"),
            0,
            policy,
        )
        assert transport.order == ["ack", "enqueue"]

    asyncio.run(body())
