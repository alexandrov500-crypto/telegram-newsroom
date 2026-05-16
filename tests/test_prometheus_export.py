from __future__ import annotations

from utils.metrics import inc, reset_metrics
from utils.prometheus_export import render_prometheus_metrics


def test_prometheus_render_includes_counters() -> None:
    reset_metrics()
    inc("posts_collected", 2)
    txt = render_prometheus_metrics({"counters": {"posts_collected": 2}, "gauges": {}})
    assert "newsroom_posts_collected" in txt
    assert "HELP" in txt


def test_prometheus_empty_snapshot() -> None:
    reset_metrics()
    txt = render_prometheus_metrics({"counters": {}, "gauges": {}})
    assert "newsroom_metrics_empty" in txt
