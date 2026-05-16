"""Soak harness smoke and cycle tests."""

from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from tests.soak.harness import SoakHarness, simulate_wal_churn
from utils import metrics as metrics_mod
from utils.soak_simulation import run_soak_simulation


def test_soak_harness_cycles_bounded(tmp_path) -> None:
    h = SoakHarness(work_dir=tmp_path / "soak")
    calls = {"n": 0}

    def tick() -> None:
        calls["n"] += 1

    res = h.run_cycles([("tick", tick)] * 5)
    assert res.ok
    assert calls["n"] == 5
    h.write_artifacts(res)
    assert (tmp_path / "soak" / "soak_harness_report.json").is_file()


def test_soak_simulation_in_harness(tmp_path) -> None:
    rt = tmp_path / "rt"
    rt.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rt))

    async def cycle() -> None:
        r = await run_soak_simulation(s, "low", max_ticks=12, tick_interval_sec=0.0)
        assert r.ticks == 12

    h = SoakHarness(work_dir=tmp_path / "h")
    res = asyncio.run(h.run_async_cycles([("soak_ticks", cycle)]))
    assert res.ok
    metrics_mod.reset_metrics()


def test_wal_churn_observed(tmp_path) -> None:
    db = tmp_path / "churn.db"
    wal1 = simulate_wal_churn(db, inserts=20)
    wal2 = simulate_wal_churn(db, inserts=20)
    assert wal2 >= wal1
