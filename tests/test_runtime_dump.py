from __future__ import annotations

import json

import pytest

from tests.conftest import minimal_test_settings
from utils.metrics import reset_metrics
from utils.runtime_dump import generate_runtime_dump


@pytest.fixture(autouse=True)
def _clean_metrics_for_dump():
    reset_metrics()
    yield


def test_dump_json_serializable_and_masks_secrets(monkeypatch):
    monkeypatch.setattr("utils.diagnostics.process_uptime_sec", lambda: 42.0)
    monkeypatch.setattr("utils.diagnostics.asyncio_task_count", lambda: 2)
    settings = minimal_test_settings()
    dump = generate_runtime_dump(settings, events_limit=8)
    raw = json.dumps(dump, default=str)
    assert "sk-test-key-for-unit-tests" not in raw
    assert "<redacted>" in raw
    assert dump["schema_version"] == 1
    assert "sanitized_settings" in dump
    assert "active_locks" in dump
    assert "tick_statistics" in dump


def test_dump_schema_stable_keys():
    settings = minimal_test_settings()
    keys = sorted(generate_runtime_dump(settings).keys())
    assert keys == sorted(
        [
            "schema_version",
            "uptime_sec",
            "runtime_snapshot",
            "metrics",
            "scheduler_state",
            "active_locks",
            "tick_statistics",
            "recent_runtime_events",
            "sanitized_settings",
        ]
    )


def test_two_dumps_equal_when_frozen_diagnostics(monkeypatch):
    monkeypatch.setattr("utils.runtime_dump.process_uptime_sec", lambda: 5.0)
    monkeypatch.setattr("utils.diagnostics.asyncio_task_count", lambda: 1)
    settings = minimal_test_settings()
    a = generate_runtime_dump(settings, events_limit=0)
    b = generate_runtime_dump(settings, events_limit=0)
    assert a == b
