"""Unified execution gates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ops.execution_gates import evaluate_publish_gate


def test_global_publish_pause_blocks(monkeypatch, tmp_path):
    s = SimpleNamespace(
        runtime_state_dir=str(tmp_path),
        global_publish_pause=True,
    )
    d = evaluate_publish_gate(s)
    assert d.allowed is False
    assert d.layer == "env"
