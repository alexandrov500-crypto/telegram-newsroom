"""P0.5 collector channel profiling events."""

from __future__ import annotations

import logging

from collector.channel_profile import ChannelCollectStats


def test_channel_collect_stats_summary_fields(caplog) -> None:
    caplog.set_level(logging.INFO)
    stats = ChannelCollectStats(channel="@cb_economics")
    stats.emit_start()
    stats.record_scan()
    stats.record_fetched()
    stats.record_dedup()
    stats.emit_runtime()
    stats.emit_summary()
    joined = " ".join(r.message for r in caplog.records)
    assert "collector.channel_start" in joined
    assert "collector.channel_runtime" in joined
    assert "collector.channel_summary" in joined
    assert "@cb_economics" in joined
