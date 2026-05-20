from __future__ import annotations

from app.dependency_state import AggregateStatus, DependencyStatus, RuntimeDependencyState


def test_aggregate_unhealthy_only_when_db_unavailable() -> None:
    s = RuntimeDependencyState()
    s.openai = s.openai.__class__(DependencyStatus.DEGRADED, detail="region")
    assert s.aggregate_status() == AggregateStatus.DEGRADED

    s.database = s.database.__class__(DependencyStatus.UNAVAILABLE, detail="down")
    assert s.aggregate_status() == AggregateStatus.UNHEALTHY


def test_health_payload_v2_shape() -> None:
    s = RuntimeDependencyState()
    s.startup_complete = True
    payload = s.health_payload()
    assert payload["status"] == "healthy"
    assert "dependencies" in payload
    assert set(payload["dependencies"]) == {"database", "telegram_api", "openai", "telethon"}
