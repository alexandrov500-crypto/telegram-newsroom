"""Recovery override flags for silent-pipeline incidents."""

from __future__ import annotations

import os

import pytest

from app.recovery import pipeline_overrides as po


@pytest.fixture(autouse=True)
def _clear_recovery_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FORCE_AI_PIPELINE_ENABLED",
        "MINIMAL_PIPELINE_MODE",
        "MINIMAL_NEWSROOM_MODE",
        "FORCE_PUBLISH_BYPASS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_upstream_state_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_AI_PIPELINE_ENABLED", "true")
    assert po.upstream_pipeline_state(ctx_ai_enabled=False, circuit_allows=False) == "forced"


def test_effective_ai_gate_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_AI_PIPELINE_ENABLED", "true")

    class _Circuit:
        def allow_request(self) -> bool:
            return False

    assert po.effective_ai_gate_open(ctx_ai_enabled=False, circuit=_Circuit()) is True


def test_minimal_bypasses_final_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.editorial.final_publish_gate import evaluate_final_publish_gate
    from tests.conftest import minimal_test_settings

    monkeypatch.setenv("MINIMAL_PIPELINE_MODE", "true")
    gate = evaluate_final_publish_gate(
        content="Tabloid BREAKING!!!",
        sources="[]",
        settings=minimal_test_settings(),
        operator_approved=False,
    )
    assert gate.allowed is True
    assert gate.reason == "recovery_bypass"


def test_recovery_bypass_active(monkeypatch: pytest.MonkeyPatch) -> None:
    assert po.recovery_bypass_active() is False
    monkeypatch.setenv("FORCE_PUBLISH_BYPASS", "1")
    assert po.recovery_bypass_active() is True
