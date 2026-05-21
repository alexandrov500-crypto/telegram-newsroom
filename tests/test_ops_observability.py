"""Observability: timeline, incidents, runtime API, structured logs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.dependency_state import reset_dependency_state
from ops.incidents.triggers import maybe_trigger_incident, reset_incident_triggers_for_tests
from ops.log_ring import append_log_line, recent_log_lines, reset_log_ring_for_tests
from ops.runtime_timeline import record_timeline, reset_timeline_for_tests, timeline_snapshot
from ops.incidents.bundle import collect_incident_payload, write_incident_bundle_sync
from ops.runtime_api import runtime_timeline_payload, runtime_circuit_payload
from ops.recovery_telemetry import reset_recovery_telemetry_for_tests
from utils.metrics import reset_metrics
from utils.structured_log import log_event, reset_log_event_id_sequence_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_dependency_state()
    reset_timeline_for_tests()
    reset_incident_triggers_for_tests()
    reset_log_ring_for_tests()
    reset_metrics()
    reset_recovery_telemetry_for_tests()
    reset_log_event_id_sequence_for_tests()
    yield


def test_timeline_newest_first():
    record_timeline("scheduler.tick.started")
    record_timeline("scheduler.tick.completed", wall_sec=1.0)
    entries = timeline_snapshot(limit=10)
    assert entries[0]["kind"] == "scheduler.tick.completed"


def test_structured_log_json_envelope(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.ops")
    log_event(logger, "runtime.boot", subsystem="runtime", phase="test")
    assert caplog.records
    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "runtime.boot"
    assert payload["runtime_id"]
    assert payload["git_sha"]
    assert "timestamp" in payload
    assert recent_log_lines(limit=5)[-1].startswith("{")


def test_incident_bundle_write(tmp_path: Path):
    append_log_line('{"event":"test"}')
    record_timeline("watchdog.exception_burst", count=10)
    path = write_incident_bundle_sync(
        incidents_dir=tmp_path,
        trigger="test_trigger",
        detail={"test": True},
    )
    assert path and Path(path).is_file()
    assert Path(path).stat().st_size > 100
    payload = collect_incident_payload(trigger="x")
    assert payload["runtime_id"]
    env = payload.get("env_whitelist") or {}
    for k, v in env.items():
        if "KEY" in k.upper() or "TOKEN" in k.upper() or "SECRET" in k.upper():
            assert v == "***REDACTED***"


def test_runtime_api_shapes():
    record_timeline("runtime.degraded", dependency="openai")
    tl = runtime_timeline_payload(limit=5)
    assert "entries" in tl
    circ = runtime_circuit_payload()
    assert "circuit" in circ


def test_incident_trigger_cooldown(ephemeral_newsroom_settings, tmp_path: Path):
    settings = ephemeral_newsroom_settings
    object.__setattr__(settings, "runtime_state_dir", str(tmp_path / "rt"))
    maybe_trigger_incident(settings, "test_a", force=True)
    maybe_trigger_incident(settings, "test_a", force=False)
    bundles = list((tmp_path / "rt" / "incidents").glob("*.tar.gz"))
    assert len(bundles) >= 1
