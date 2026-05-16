from __future__ import annotations

import asyncio

import pytest

from tests.conftest import minimal_test_settings
from utils import metrics as metrics_mod
from utils.soak_simulation import (
    PROFILE_HANDLERS,
    collect_bounded_state_report,
    run_soak_simulation,
    soak_result_to_dict,
)


@pytest.mark.parametrize("profile", sorted(PROFILE_HANDLERS))
def test_soak_simulation_runs_bounded(profile: str, tmp_path) -> None:
    rt = tmp_path / "rt"
    rt.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rt))

    async def body() -> None:
        r = await run_soak_simulation(
            s, profile, duration_sec=0.01, tick_interval_sec=0.0, max_ticks=8
        )
        assert r.ticks == 8
        rep = collect_bounded_state_report(s)
        assert rep["timeline_events"] <= 240
        assert rep["duplicate_burst"] >= 0
        d = soak_result_to_dict(r)
        assert d["profile"] == profile

    asyncio.run(body())
    metrics_mod.reset_metrics()


def test_soak_multi_hour_equivalent_ticks(tmp_path) -> None:
    """Wall-clock multi-hour soak is represented by many ticks in real deployments; CI uses a handful."""
    rt = tmp_path / "soak_rt"
    rt.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rt))
    r = asyncio.run(run_soak_simulation(s, "medium", max_ticks=120, tick_interval_sec=0.0))
    assert r.ticks == 120
    assert r.bounded_report.get("ok") is True
