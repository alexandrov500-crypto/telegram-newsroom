"""Pipeline state reconciler — unstick ai_pipeline_enabled from startup DEGRADED."""

from __future__ import annotations

import pytest

from app.dependency_state import DependencyStatus, get_dependency_state, reset_dependency_state
from app.openai_circuit import get_openai_circuit, reset_openai_circuit_for_tests
from app.recovery.pipeline_state_reconciler import reconcile_pipeline_state


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_dependency_state()
    reset_openai_circuit_for_tests()
    yield
    reset_dependency_state()
    reset_openai_circuit_for_tests()


def test_reconcile_enables_on_backlog_when_openai_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    deps = get_dependency_state()
    deps.set_dependency("openai", status=DependencyStatus.DEGRADED, detail="startup")
    deps.ai_pipeline_enabled = False
    get_openai_circuit().reset_for_tests()

    get_openai_circuit().force_open("test_stuck_open")
    rec = reconcile_pipeline_state(raw_unprocessed=10, apply=True)
    assert rec.ai_pipeline_enabled is True
    assert rec.summarize_enabled is True
    assert "backlog" in rec.reason and rec.summarize_enabled
    assert get_dependency_state().ai_pipeline_enabled is True


def test_reconcile_force_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = get_dependency_state()
    deps.ai_pipeline_enabled = False
    monkeypatch.setenv("FORCE_AI_PIPELINE_ENABLED", "true")

    rec = reconcile_pipeline_state(raw_unprocessed=0, apply=True)
    assert rec.ai_pipeline_enabled is True
    assert rec.reason == "force_ai_pipeline_enabled"
