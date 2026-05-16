from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.conftest import minimal_test_settings
from utils.runtime_dump import generate_runtime_dump
from utils.runtime_state_store import (
    load_latest_runtime_snapshot,
    save_runtime_snapshot,
    snapshot_dir,
    try_save_runtime_snapshot,
)


def test_save_load_roundtrip(tmp_path):
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "rt"))
    p = save_runtime_snapshot(s, "test_reason", events_limit=8)
    assert p.is_file()
    loaded = load_latest_runtime_snapshot(s)
    assert loaded is not None
    assert loaded.get("reason") == "test_reason"
    assert loaded.get("diagnostics_dump") is not None
    raw = json.dumps(loaded, default=str)
    assert "sk-test-key-for-unit-tests" not in raw


def test_load_latest_skips_corrupt_file(tmp_path):
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "rt2"))
    d = snapshot_dir(s)
    d.mkdir(parents=True)
    good = {
        "schema_version": 2,
        "recorded_at_unix": time.time(),
        "recorded_at_iso": "2099-01-01T00:00:00Z",
        "reason": "good",
        "runtime_snapshot": {},
        "metrics": {},
        "diagnostics_dump": generate_runtime_dump(s, events_limit=2),
        "scheduler_state": {},
        "recent_errors": [],
        "recent_runtime_events_tail": [],
    }
    (d / "snapshot_1_good.json").write_text(json.dumps(good), encoding="utf-8")
    (d / "snapshot_2_bad.json").write_text("{not json", encoding="utf-8")
    # newer corrupt first by mtime
    time.sleep(0.02)
    (d / "snapshot_3_bad.json").write_text("corrupt", encoding="utf-8")
    loaded = load_latest_runtime_snapshot(s)
    assert loaded is not None
    assert loaded.get("reason") == "good"


def test_try_save_never_raises(monkeypatch, tmp_path):
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "rt3"))

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("utils.runtime_state_store.save_runtime_snapshot", boom)
    try_save_runtime_snapshot(s, "x")  # no exception


def test_deterministic_top_level_schema(tmp_path):
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "rt4"))
    save_runtime_snapshot(s, "schema_probe", events_limit=4)
    data = load_latest_runtime_snapshot(s)
    assert set(data.keys()) >= {
        "schema_version",
        "recorded_at_unix",
        "reason",
        "diagnostics_dump",
        "metrics",
        "runtime_snapshot",
    }


def test_maybe_flush_respects_interval(monkeypatch, tmp_path):
    import utils.runtime_state_store as rs

    s = minimal_test_settings(
        runtime_state_dir=str(tmp_path / "flush"),
        runtime_event_flush_interval_sec=100,
    )
    rs.reset_runtime_flush_clock_for_tests()
    calls = {"n": 0}

    def rec(*a, **k):
        calls["n"] += 1

    monkeypatch.setattr(rs, "try_save_runtime_snapshot", rec)
    clock = {"t": 0.0}

    def fake_mono() -> float:
        return float(clock["t"])

    monkeypatch.setattr(rs, "_wall_mono", fake_mono)
    rs.maybe_flush_runtime_events_to_snapshot(s)
    assert calls["n"] == 1
    clock["t"] = 10.0
    rs.maybe_flush_runtime_events_to_snapshot(s)
    assert calls["n"] == 1
    clock["t"] = 150.0
    rs.maybe_flush_runtime_events_to_snapshot(s)
    assert calls["n"] == 2
