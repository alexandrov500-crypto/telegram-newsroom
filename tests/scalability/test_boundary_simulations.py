"""Scalability envelope simulations."""

from __future__ import annotations

import asyncio

from tests.scalability.simulations import (
    simulate_evidence_growth,
    simulate_queue_burst_depth,
    simulate_restore_duration_estimate,
    simulate_retry_amplification,
    simulate_wal_pressure,
)
from tests.conftest import minimal_test_settings
from workers import state as worker_state


def test_queue_burst_bounded_by_cap() -> None:
    r = simulate_queue_burst_depth(bursts=50, cap=100)
    assert r["peak_depth"] <= 100


def test_retry_amplification_detects_saturation() -> None:
    r = simulate_retry_amplification(events=50, window_sec=60.0, threshold=40)
    assert r["saturated"] is True


def test_wal_pressure_grows_with_load(tmp_path) -> None:
    db = tmp_path / "scale.db"
    small = simulate_wal_pressure(db, rounds=2, inserts_per_round=10)
    large = simulate_wal_pressure(db, rounds=20, inserts_per_round=50)
    assert large["wal_bytes"] >= small["wal_bytes"]


def test_evidence_growth_linear(tmp_path) -> None:
    r = simulate_evidence_growth(tmp_path / "od", files=5, bytes_each=1000)
    assert r["file_count"] == 5
    assert r["total_bytes"] >= 5000


def test_restore_duration_scales_with_size() -> None:
    small = simulate_restore_duration_estimate(10, bytes_per_file=1000)
    large = simulate_restore_duration_estimate(100, bytes_per_file=10000)
    assert large > small


def test_worker_retry_burst_integration() -> None:
    async def body() -> None:
        worker_state.reset_worker_runtime_state_for_tests()
        s = minimal_test_settings(runtime_retry_storm_count=5, runtime_retry_storm_window_sec=60.0)
        for _ in range(10):
            await worker_state.on_retry()
        d = await worker_state.collect_runtime_diag(s)
        assert int(d["retry_burst_window"]) == 10

    asyncio.run(body())


def test_scalability_diagnostics_tool_ok() -> None:
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo / "tools/scalability_diagnostics.py")],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["read_only"] is True
    assert data["topology_hint"] in ("T1", "T2", "T2-risky")
