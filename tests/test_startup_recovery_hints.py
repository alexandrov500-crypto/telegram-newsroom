from __future__ import annotations

import logging

import pytest

from tests.conftest import minimal_test_settings
from utils.runtime_state_store import save_runtime_snapshot
from utils.startup_recovery_hints import log_startup_recovery_hints_if_any


def test_no_hint_for_shutdown_snapshot(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "h1"))
    save_runtime_snapshot(s, "shutdown", events_limit=4)
    log_startup_recovery_hints_if_any(s)
    assert "startup.recovery_hint" not in caplog.text


def test_hint_logged_for_inner_failure_snapshot(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "h2"))
    save_runtime_snapshot(s, "pipeline_inner_failed", events_limit=4)
    log_startup_recovery_hints_if_any(s)
    assert any("startup.recovery_hint" in r.message for r in caplog.records)
