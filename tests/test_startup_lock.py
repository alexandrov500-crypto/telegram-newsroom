from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.startup_lock import (
    acquire_runtime_startup_lock,
    release_runtime_startup_lock,
    reset_startup_lock_for_tests,
)
from tests.conftest import minimal_test_settings


@pytest.fixture(autouse=True)
def _reset_lock_state():
    reset_startup_lock_for_tests()
    yield
    reset_startup_lock_for_tests()


def test_acquire_and_release_startup_lock(tmp_path: Path):
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "runtime"))
    acquire_runtime_startup_lock(s)
    lock = tmp_path / "runtime" / "start.lock"
    assert lock.is_file()
    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    release_runtime_startup_lock(s)
    assert not lock.exists()


def test_stale_lock_removed_when_pid_dead(tmp_path: Path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    lock = runtime / "start.lock"
    lock.write_text('{"pid": 999999999, "started_at_unix": 0}\n', encoding="utf-8")
    s = minimal_test_settings(runtime_state_dir=str(runtime))
    acquire_runtime_startup_lock(s)
    assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
    release_runtime_startup_lock(s)


def test_live_lock_blocks_second_acquire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import app.startup_lock as startup_lock

    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "runtime"))
    acquire_runtime_startup_lock(s)
    lock = tmp_path / "runtime" / "start.lock"
    foreign_pid = 424242
    lock.write_text(json.dumps({"pid": foreign_pid, "started_at_unix": 0}) + "\n", encoding="utf-8")
    reset_startup_lock_for_tests()
    monkeypatch.setattr(startup_lock, "_pid_alive", lambda pid: pid == foreign_pid)
    with pytest.raises(RuntimeError, match="Another newsroom process holds startup lock"):
        acquire_runtime_startup_lock(s)
    release_runtime_startup_lock(s)
