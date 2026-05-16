"""Memory and resource stability (lightweight)."""

from __future__ import annotations

from utils.resource_stability import analyze_memory_trend, analyze_task_growth, snapshot_resources


def test_resource_snapshots_bounded_list() -> None:
    samples = [snapshot_resources() for _ in range(5)]
    assert all(s.ts for s in samples)
    mem = analyze_memory_trend(samples)
    assert mem["status"] in ("OK", "WARNING", "insufficient_data")
    tasks = analyze_task_growth(samples)
    assert "status" in tasks


def test_no_unbounded_metric_growth_in_soak() -> None:
    from utils.metrics import export_snapshot, inc, reset_metrics

    reset_metrics()
    for _ in range(50):
        inc("posts_collected", 1)
    snap = export_snapshot()
    assert int(snap["counters"]["posts_collected"]) == 50
