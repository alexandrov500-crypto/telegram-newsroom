from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.ingestion.idempotency import (
    init_idempotency_store,
    message_fingerprint,
    reset_idempotency_store_for_tests,
)
from app.ops.runtime.active_runtime import (
    active_runtime_path,
    clear_active_runtime,
    load_active_runtime,
    register_active_runtime,
)
from app.ops.runtime.pipeline_gate import allow_processing, is_singleton_owner
from app.ops.runtime.singleton_guard import (
    RuntimeSingletonGuard,
    reset_singleton_guard_for_tests,
)
from tests.conftest import minimal_test_settings


@pytest.fixture(autouse=True)
def _reset_runtime_ops():
    reset_singleton_guard_for_tests()
    reset_idempotency_store_for_tests()
    yield
    reset_singleton_guard_for_tests()
    reset_idempotency_store_for_tests()


def test_singleton_guard_acquire_release(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    g = RuntimeSingletonGuard(rd)
    assert g.acquire()
    assert g.is_owner()
    lock = tmp_path / "runtime" / "newsroom.lock"
    assert lock.is_file()
    g.release()
    assert not g.is_owner()


def test_second_acquire_fails_while_held(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    g1 = RuntimeSingletonGuard(rd)
    g2 = RuntimeSingletonGuard(rd)
    assert g1.acquire()
    assert not g2.acquire()
    g1.release()
    assert g2.acquire()
    g2.release()


def test_active_runtime_atomic_write(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    register_active_runtime(rd, runtime_id="rt-test-1", pid=12345, hostname="testhost")
    data = load_active_runtime(rd)
    assert data is not None
    assert data["runtime_id"] == "rt-test-1"
    assert data["pid"] == 12345
    assert data["hostname"] == "testhost"
    assert active_runtime_path(rd).is_file()
    clear_active_runtime(rd, expected_pid=12345)
    assert not active_runtime_path(rd).exists()


def test_idempotency_try_claim(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    store = init_idempotency_store(rd)
    assert store.try_claim("@news", 1001)
    assert not store.try_claim("@news", 1001)
    assert store.try_claim("@news", 1002)
    fp = message_fingerprint("@news", 1001)
    assert len(fp) == 64


def test_pipeline_gate_requires_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RUNTIME_SINGLETON_DISABLED", "false")
    rd = str(tmp_path / "runtime")
    g = RuntimeSingletonGuard(rd)
    assert not is_singleton_owner()
    assert allow_processing()[0] is False
    assert g.acquire()
    from app.ops.runtime import singleton_guard as sg

    assert sg._guard is g
    assert is_singleton_owner()
    assert allow_processing()[0] is True
    g.release()


def test_enforce_singleton_exits_when_lock_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Second guard cannot acquire while first holds flock (duplicate container behavior)."""
    monkeypatch.setenv("RUNTIME_SINGLETON_DISABLED", "false")
    rd = str(tmp_path / "runtime")
    g1 = RuntimeSingletonGuard(rd)
    g2 = RuntimeSingletonGuard(rd)
    assert g1.acquire()
    assert not g2.acquire()
    g1.release()
