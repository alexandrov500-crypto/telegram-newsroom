from __future__ import annotations

import asyncio

import pytest

from bot.observability.loop_registry import (
    LoopHeartbeatRegistry,
    reset_and_configure_loop_registry,
)
from bot.runtime.loop_manifest import runtime_loops_classification
from bot.runtime.profile import (
    RuntimeProfile,
    capabilities_for,
    filter_watchdog_stalled_names,
    reset_runtime_capabilities_cache,
)


@pytest.fixture(autouse=True)
def _clear_profile_cache() -> None:
    reset_runtime_capabilities_cache()
    yield
    reset_runtime_capabilities_cache()


def test_minimal_pilot_registry_excludes_research_loops() -> None:
    caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
    reg = reset_and_configure_loop_registry(caps)
    names = set(reg.snapshot().keys())
    assert "pilot-ops" in names
    assert "rss-ingestion" in names
    assert "reliability-probe" in names
    assert "autonomous-runtime" in names
    assert "epistemic-integrity" not in names
    assert "federated-cognitive-mesh" not in names
    assert "cognitive-runtime" not in names
    assert "operator-signal-hub" not in names
    assert "operations-platform" not in names


def test_heartbeat_does_not_auto_register_disabled_loop() -> None:
    caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
    reg = reset_and_configure_loop_registry(caps)
    reg.heartbeat("epistemic-integrity", 0.1)
    assert "epistemic-integrity" not in reg.snapshot()


def test_stalled_research_loops_not_reported_when_unregistered() -> None:
    caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
    reg = reset_and_configure_loop_registry(caps)
    reg.register("epistemic-integrity", 10.0)
    assert "epistemic-integrity" not in reg.snapshot()
    assert reg.stalled_loops() == []


def test_minimal_disabled_classification() -> None:
    caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
    classified = runtime_loops_classification(caps)
    assert "epistemic-integrity" in classified["disabled"]
    assert "pilot-ops" in classified["active"]
    assert "autonomous-runtime" in classified["passive"]


def test_filter_stalled_requires_running_task() -> None:
    async def _run() -> None:
        caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
        reg = reset_and_configure_loop_registry(caps)
        reg._loops["pilot-ops"].last_tick_monotonic = 0.0  # force stall

        async def _noop() -> None:
            await asyncio.sleep(3600)

        assert filter_watchdog_stalled_names(["pilot-ops"], caps=caps, registry=reg) == []

        task = asyncio.create_task(_noop(), name="pilot-ops")
        try:
            assert filter_watchdog_stalled_names(["pilot-ops"], caps=caps, registry=reg) == [
                "pilot-ops",
            ]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(_run())
