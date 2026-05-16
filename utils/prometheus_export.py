"""Prometheus text exposition from in-process counters (no client library)."""

from __future__ import annotations

from typing import Any


def _line(name: str, help_text: str, typ: str, value: float | int) -> str:
    return f"# HELP {name} {help_text}\n# TYPE {name} {typ}\n{name} {value}\n"


def render_prometheus_metrics(metrics_export: dict[str, Any] | None) -> str:
    """Render counters/gauges from ``utils.metrics.export_snapshot()`` shape."""
    snap = metrics_export or {}
    ctr = dict(snap.get("counters") or {})
    gauges = dict(snap.get("gauges") or {})
    lines: list[str] = []
    interesting = sorted(set(ctr) | set(gauges))
    for name in interesting:
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in str(name).lower())
        metric = f"newsroom_{safe}"
        if name in ctr:
            lines.append(_line(metric, f"newsroom counter {name}", "counter", int(ctr[name])))
        elif name in gauges:
            lines.append(_line(metric, f"newsroom gauge {name}", "gauge", float(gauges[name])))
    if not lines:
        return _line("newsroom_metrics_empty", "no counters or gauges yet", "gauge", 0)
    return "".join(lines)
