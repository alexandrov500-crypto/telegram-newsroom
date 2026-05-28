"""Runtime control modes (stability freeze)."""

from __future__ import annotations

import json

import pytest

from app.ops.runtime_control import (
    RuntimeControlMode,
    infer_mode_from_env,
    load_runtime_control,
    persist_runtime_control,
    publish_allowed_by_control,
    set_runtime_control,
    sync_runtime_control_from_env,
)


def test_global_publish_pause_blocks_publish_not_mode(monkeypatch, tmp_path):
    from app.ops.runtime_control import publish_allowed_by_control

    monkeypatch.setenv("GLOBAL_PUBLISH_PAUSE", "true")
    monkeypatch.delenv("RUNTIME_CONTROL_MODE", raising=False)
    monkeypatch.delenv("BURNIN_OPENAI_ALWAYS_FALLBACK", raising=False)
    monkeypatch.delenv("BURNIN_SOFT_GOVERNANCE", raising=False)
    monkeypatch.setenv("MEDIA_PIPELINE_ENABLED", "true")
    rd = str(tmp_path)
    persist_runtime_control(rd, RuntimeControlMode.NORMAL)
    assert infer_mode_from_env() == RuntimeControlMode.NORMAL
    assert publish_allowed_by_control(rd) is False


def test_paused_blocks_publish(tmp_path):
    rd = str(tmp_path)
    persist_runtime_control(rd, RuntimeControlMode.NORMAL, reason="test")
    assert publish_allowed_by_control(rd) is True
    set_runtime_control(rd, RuntimeControlMode.PAUSED, reason="unit_test")
    assert publish_allowed_by_control(rd) is False


def test_sync_from_env_burnin_soft(monkeypatch, tmp_path):
    rd = str(tmp_path)
    monkeypatch.delenv("GLOBAL_PUBLISH_PAUSE", raising=False)
    monkeypatch.delenv("RUNTIME_CONTROL_MODE", raising=False)
    monkeypatch.setenv("BURNIN_OPENAI_ALWAYS_FALLBACK", "true")
    monkeypatch.delenv("BURNIN_SOFT_GOVERNANCE", raising=False)
    mode = sync_runtime_control_from_env(rd)
    assert mode == RuntimeControlMode.SOFT_DEGRADED
    path = tmp_path / "runtime_control.json"
    data = json.loads(path.read_text())
    assert data["mode"] == "soft_degraded"


def test_load_respects_persisted_when_no_env_override(monkeypatch, tmp_path):
    rd = str(tmp_path)
    monkeypatch.delenv("RUNTIME_CONTROL_MODE", raising=False)
    monkeypatch.delenv("GLOBAL_PUBLISH_PAUSE", raising=False)
    persist_runtime_control(rd, RuntimeControlMode.TEXT_ONLY)
    assert load_runtime_control(rd) == RuntimeControlMode.TEXT_ONLY
