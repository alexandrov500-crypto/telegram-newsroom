"""Node role and execution lease (production hardening)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.ops.runtime.execution_lease import (
    clear_stale_lease,
    is_lease_stale,
    read_lease,
    release_lease,
    try_acquire_lease,
    write_execution_intent,
)
from app.ops.runtime.node_role import RuntimeNodeRole, resolve_execution_profile


class _Settings:
    runtime_state_dir: str
    telegram_polling_enabled: bool = True
    deployment_profile: str = "development"

    def __init__(self, rd: str) -> None:
        self.runtime_state_dir = rd


def test_control_plane_disables_polling(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNTIME_NODE_ROLE", "control")
    monkeypatch.delenv("RUNTIME_CONTROL_ALLOW_PIPELINE", raising=False)
    s = _Settings(str(tmp_path))
    profile = resolve_execution_profile(s)
    assert profile.node_role == RuntimeNodeRole.CONTROL
    assert profile.polling_enabled is False
    assert profile.scheduler_enabled is False
    assert profile.publish_enabled is False


def test_execution_intent_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNTIME_NODE_ROLE", "worker")
    write_execution_intent(str(tmp_path), role="control", reason="test")
    profile = resolve_execution_profile(_Settings(str(tmp_path)))
    assert profile.node_role == RuntimeNodeRole.CONTROL


def test_lease_acquire_and_stale(tmp_path: Path) -> None:
    rd = str(tmp_path)
    ok, lease = try_acquire_lease(rd, owner_id="a", runtime_id="r1", node_role="worker")
    assert ok and lease is not None
    ok2, lease2 = try_acquire_lease(rd, owner_id="b", runtime_id="r2", node_role="worker")
    assert not ok2 and lease2 is not None
    assert release_lease(rd, owner_id="a")
    ok3, _ = try_acquire_lease(rd, owner_id="b", runtime_id="r2", node_role="worker", force=True)
    assert ok3
    path = tmp_path / "execution_lease.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["heartbeat_unix"] = time.time() - 500
    path.write_text(json.dumps(data), encoding="utf-8")
    stale = read_lease(rd)
    assert stale is not None and is_lease_stale(stale)
    assert clear_stale_lease(rd)
