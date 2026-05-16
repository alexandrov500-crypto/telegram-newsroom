from __future__ import annotations

import asyncio
import threading

from utils.metrics import (
    avg_pipeline_duration_sec,
    export_snapshot,
    inc,
    record_pipeline_duration,
    reset_metrics,
    set_gauge,
    snapshot,
)


def test_increment_counters_and_gauges():
    reset_metrics()
    inc("posts_collected", 3)
    inc("posts_collected", 2)
    set_gauge("queue_depth", 4.5)
    snap = snapshot()
    assert snap["posts_collected"] == 5
    ex = export_snapshot()
    assert ex["counters"]["posts_collected"] == 5
    assert ex["gauges"]["queue_depth"] == 4.5


def test_pipeline_duration_accumulation_and_avg():
    reset_metrics()
    record_pipeline_duration(1.0)
    record_pipeline_duration(3.0)
    avg = avg_pipeline_duration_sec()
    assert avg == 2.0
    ex = export_snapshot()
    assert ex["pipeline_duration_sample_count"] == 2
    assert ex["pipeline_duration_sum_sec"] == 4.0
    assert ex["pipeline_duration_avg_sec"] == 2.0


def test_snapshot_consistency_and_reset():
    reset_metrics()
    inc("drafts_generated", 1)
    set_gauge("x", 1.0)
    a = export_snapshot()
    b = export_snapshot()
    assert a == b
    reset_metrics()
    c = export_snapshot()
    assert c["counters"]["drafts_generated"] == 0
    assert c["gauges"] == {}
    assert c["pipeline_duration_sample_count"] == 0
    assert c["pipeline_duration_avg_sec"] is None


def test_threaded_increments():
    reset_metrics()

    def worker() -> None:
        for _ in range(50):
            inc("clusters_created")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert snapshot()["clusters_created"] == 200


def test_async_gather_increments():
    reset_metrics()

    async def bump() -> None:
        inc("openai_retries")

    async def body() -> None:
        await asyncio.gather(*[bump() for _ in range(20)])

    asyncio.run(body())
    assert snapshot()["openai_retries"] == 20
