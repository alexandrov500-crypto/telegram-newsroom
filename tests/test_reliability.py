from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from bot.reliability.publish_gate import PublishGateController
from bot.reliability.runtime_health_manager import RuntimeHealthManager
from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import HealthState, IncidentSeverity, PublishMode, SubsystemName
from bot.reliability.watchdog_recovery import SubsystemWatchdog


def test_health_manager_degraded_on_stale_heartbeat() -> None:
    mgr = RuntimeHealthManager(ReliabilitySettings.from_env())
    mgr.heartbeat(SubsystemName.INGEST, ok=False, detail="stale")
    probe = mgr._probes[SubsystemName.INGEST]
    probe.last_ok_monotonic = time.monotonic() - 900
    snap = mgr.probe()
    assert snap.overall_state != HealthState.HEALTHY


def test_publish_gate_shadow_blocks() -> None:
    settings = ReliabilitySettings.from_env()
    gate = PublishGateController(settings)
    gate.set_mode(PublishMode.SHADOW)
    verdict = gate.evaluate(
        health_state=HealthState.HEALTHY,
        health_score=0.95,
        queue_depth=10,
        cognition_latency_ms=1000.0,
        telegram_failure_rate=0.0,
    )
    assert not verdict.allowed
    assert verdict.mode == PublishMode.SHADOW


def test_publish_gate_limited_requires_stability() -> None:
    settings = ReliabilitySettings(
        enabled=True,
        publish_stability_sec=3600.0,
        limited_production_cap_per_hour=5,
    )
    gate = PublishGateController(settings)
    gate.set_mode(PublishMode.LIMITED_PRODUCTION)
    verdict = gate.evaluate(
        health_state=HealthState.HEALTHY,
        health_score=0.9,
        queue_depth=5,
        cognition_latency_ms=500.0,
        telegram_failure_rate=0.0,
        operator_approved=True,
    )
    assert not verdict.allowed
    assert "stability" in verdict.reason or verdict.blockers


def test_watchdog_recovery_backoff() -> None:
    import asyncio
    settings = ReliabilitySettings(
        enabled=True,
        recovery_max_attempts=3,
        recovery_backoff_base_sec=1.0,
    )
    incidents: list[str] = []

    async def on_incident(**kwargs: object) -> None:
        incidents.append(str(kwargs.get("title")))

    wd = SubsystemWatchdog(settings)
    wd._on_incident = on_incident
    r1 = asyncio.run(
        wd.evaluate(
            stalled_loops=["rss-ingestion"],
            queue_backlog=0,
            health_state=HealthState.DEGRADED,
        )
    )
    assert r1
    r2 = asyncio.run(
        wd.evaluate(
            stalled_loops=["rss-ingestion"],
            queue_backlog=0,
            health_state=HealthState.DEGRADED,
        )
    )
    assert len(r2) == 0 or r2[0].attempt >= 1


def test_incident_severity_rank() -> None:
    assert IncidentSeverity.FATAL.rank > IncidentSeverity.ERROR.rank
