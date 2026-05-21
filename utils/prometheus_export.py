"""Prometheus text exposition from in-process counters (no client library)."""

from __future__ import annotations

from typing import Any


def _line(name: str, help_text: str, typ: str, value: float | int) -> str:
    return f"# HELP {name} {help_text}\n# TYPE {name} {typ}\n{name} {value}\n"


def _render_histogram(name: str, hist: dict[str, Any]) -> str:
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in str(name).lower())
    metric = f"newsroom_{safe}"
    buckets = hist.get("buckets") or {}
    total = int(hist.get("count") or 0)
    sum_v = float(hist.get("sum") or 0.0)
    lines = [
        f"# HELP {metric} newsroom histogram {name} (seconds)\n",
        f"# TYPE {metric} histogram\n",
    ]
    cumulative = 0
    for le, count in sorted(buckets.items(), key=lambda x: float(x[0]) if x[0] != "inf" else 1e99):
        cumulative += int(count or 0)
        le_label = "+Inf" if le == "inf" else str(le)
        lines.append(f'{metric}_bucket{{le="{le_label}"}} {cumulative}\n')
    lines.append(f"{metric}_sum {sum_v}\n")
    lines.append(f"{metric}_count {total}\n")
    return "".join(lines)


def render_prometheus_metrics(metrics_export: dict[str, Any] | None) -> str:
    """Render counters/gauges/histograms from ``utils.metrics.export_snapshot()`` shape."""
    snap = metrics_export or {}
    ctr = dict(snap.get("counters") or {})
    gauges = dict(snap.get("gauges") or {})
    histograms = dict(snap.get("histograms") or {})
    lines: list[str] = []
    interesting = sorted(set(ctr) | set(gauges))
    for name in interesting:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in str(name).lower())
        metric = f"newsroom_{safe}"
        if name in ctr:
            lines.append(_line(metric, f"newsroom counter {name}", "counter", int(ctr[name])))
        elif name in gauges:
            lines.append(_line(metric, f"newsroom gauge {name}", "gauge", float(gauges[name])))
    for name in sorted(histograms.keys()):
        lines.append(_render_histogram(name, histograms[name]))
    if not lines:
        return _line("newsroom_metrics_empty", "no counters or gauges yet", "gauge", 0)
    return "".join(lines)
