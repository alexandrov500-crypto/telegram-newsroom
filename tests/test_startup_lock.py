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


def test_acquire_and_release_startup_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNTIME_SINGLETON_DISABLED", "false")
    s = minimal_test_settings(runtime_state_dir=str(tmp_path / "runtime"))
    acquire_runtime_startup_lock(s)
    lock = tmp_path / "runtime" / "newsroom.lock"
    assert lock.is_file()
    payload = json.loads(lock.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    release_runtime_startup_lock(s)
    g3 = __import__(
        "app.ops.runtime.singleton_guard", fromlist=["RuntimeSingletonGuard"]
    ).RuntimeSingletonGuard(str(tmp_path / "runtime"))
    assert g3.acquire()
    g3.release()


def test_second_acquire_blocked_while_held(tmp_path: Path):
    from app.ops.runtime.singleton_guard import RuntimeSingletonGuard

    rd = str(tmp_path / "runtime")
    g1 = RuntimeSingletonGuard(rd)
    g2 = RuntimeSingletonGuard(rd)
    assert g1.acquire()
    assert not g2.acquire()
    g1.release()
    assert g2.acquire()
    g2.release()
