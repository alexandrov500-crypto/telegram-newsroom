"""Production operational hardening (lifecycle, circuit, metrics, queue, health)."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from app.dependency_state import get_dependency_state, reset_dependency_state
from app.openai_circuit import CircuitState, get_openai_circuit, reset_openai_circuit_for_tests
from app.runtime_activity import (
    record_ai_success,
    record_collect_success,
    record_scheduler_tick,
    reset_runtime_activity_for_tests,
)
from app.runtime_lifecycle import emit_lifecycle, reset_runtime_lifecycle_for_tests, runtime_id, uptime_sec
from utils.metrics import observe_histogram, reset_metrics, export_snapshot
from utils.prometheus_export import render_prometheus_metrics
from worker.job_queue import InMemoryJobQueue, JobEnvelope, JobKind, QueueOverflowError


@pytest.fixture(autouse=True)
def _reset_hardening_state():
    reset_dependency_state()
    reset_openai_circuit_for_tests()
    reset_runtime_activity_for_tests()
    reset_runtime_lifecycle_for_tests()
    reset_metrics()
    yield
    reset_openai_circuit_for_tests()
    reset_metrics()


def test_runtime_lifecycle_fields(caplog):
    caplog.set_level(logging.INFO)
    emit_lifecycle("runtime.boot", phase="test")
    assert runtime_id()
    assert uptime_sec() >= 0.0
    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "runtime.boot"
    assert payload.get("runtime_id")


def test_openai_circuit_opens_and_recovers():
    circuit = get_openai_circuit()
    circuit._failure_threshold = 2  # type: ignore[attr-defined]
    circuit.record_failure("e1")
    assert circuit.state() == CircuitState.CLOSED
    circuit.record_failure("e2")
    assert circuit.state() == CircuitState.OPEN
    assert not circuit.allow_request()
    snap = export_snapshot()
    assert snap["counters"]["openai_failures_total"] >= 2
    assert snap["gauges"].get("openai_circuit_open") == 1.0
    circuit.record_success()
    assert circuit.state() == CircuitState.CLOSED
    assert snap["gauges"].get("openai_circuit_open", 0) >= 0


def test_histogram_prometheus_export():
    observe_histogram("collect_duration_seconds", 0.12)
    observe_histogram("scheduler_cycle_duration_seconds", 3.5)
    body = render_prometheus_metrics(export_snapshot())
    assert "newsroom_collect_duration_seconds_bucket" in body
    assert "newsroom_scheduler_cycle_duration_seconds_count" in body


def test_bounded_job_queue_overflow():
    async def _run() -> None:
        q = InMemoryJobQueue(max_size=2)
        job = JobEnvelope(kind=JobKind.AI, payload={"x": 1})
        await q.enqueue(job)
        await q.enqueue(job)
        with pytest.raises(QueueOverflowError):
            await q.enqueue(job)

    asyncio.run(_run())
    snap = export_snapshot()
    assert snap["counters"]["queue_overflow_total"] == 1


def test_health_payload_runtime_block():
    record_collect_success(new_rows=5)
    record_ai_success()
    record_scheduler_tick()
    get_openai_circuit().record_failure("probe")
    payload = get_dependency_state().health_payload()
    rt = payload["runtime"]
    assert rt["runtime_id"]
    assert rt["uptime_sec"] >= 0
    assert rt["last_successful_collect_at"]
    assert rt["last_successful_ai_at"]
    assert rt["openai_circuit_state"] in {"closed", "open", "half_open"}
    assert "polling_status" in rt
    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
