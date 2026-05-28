"""Reliability matrix — operational invariants."""

from __future__ import annotations

import pytest

from app.ops.runtime.node_role import RuntimeNodeRole, resolve_execution_profile
from app.reliability.failed_draft_recovery import is_publish_failure_retryable
from app.reliability.invariants import (
    InvariantSeverity,
    assert_startup_invariants,
    check_runtime_config_invariants,
)
from db.draft_lifecycle import is_transition_allowed
from ops.alert_discipline import AlertSeverity, reset_alert_discipline_for_tests, should_emit_alert
from tests.conftest import minimal_test_settings


class _Settings:
    runtime_state_dir = "var/runtime"
    telegram_polling_enabled = True
    deployment_profile = "development"
    newsroom_worker_url = ""


def test_draft_lifecycle_monotonic_terminal() -> None:
    assert is_transition_allowed("published", "pending") is False
    assert is_transition_allowed("rejected", "approved") is False
    assert is_transition_allowed("failed", "pending") is True


def test_control_plane_polling_invariant_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_NODE_ROLE", "control")
    s = minimal_test_settings(telegram_polling_enabled=True, runtime_node_role="control")
    with pytest.raises(RuntimeError, match="incompatible|invariant"):
        from app.startup_validation import validate_settings_for_launch

        validate_settings_for_launch(s)


def test_publish_retryable_matrix() -> None:
    assert is_publish_failure_retryable(reason="Connection timeout") is True
    assert is_publish_failure_retryable(reason="desk_reject:quality") is False


def test_config_invariants_worker_role() -> None:
    import os

    os.environ["RUNTIME_NODE_ROLE"] = "worker"
    profile = resolve_execution_profile(_Settings())
    assert profile.node_role == RuntimeNodeRole.WORKER
    checks = check_runtime_config_invariants(_Settings())
    critical_fail = [c for c in checks if not c.ok and c.severity == InvariantSeverity.CRITICAL]
    assert not critical_fail


def test_alert_cooldown_suppresses_duplicate() -> None:
    reset_alert_discipline_for_tests()
    assert should_emit_alert("pipeline_stalled", severity=AlertSeverity.CRITICAL) is True
    assert should_emit_alert("pipeline_stalled", severity=AlertSeverity.CRITICAL) is False


def test_assert_startup_invariants_passes_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_NODE_ROLE", "worker")
    s = minimal_test_settings(runtime_node_role="worker", telegram_polling_enabled=True)
    assert_startup_invariants(s)
