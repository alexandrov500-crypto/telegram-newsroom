"""Operational anomaly detectors for pre-launch hardening."""

from __future__ import annotations

import time
from typing import Any

from utils.metrics import export_snapshot


def detect_newsroom_anomalies(*, runtime_dir: str | None = None) -> dict[str, Any]:
    snap = export_snapshot()
    counters = snap.get("counters") or {}
    alerts: list[dict[str, str]] = []

    pub_ok = int(counters.get("publish_success_total", 0))
    pub_fail = int(counters.get("publish_failed_total", 0))
    if pub_fail > 0 and pub_ok > 0 and pub_fail / max(1, pub_ok + pub_fail) > 0.25:
        alerts.append({"kind": "publish_failure_spike", "severity": "warning"})

    recent_pub = int(counters.get("published_last_hour_total", 0))
    if recent_pub > 20:
        alerts.append({"kind": "spam_burst", "severity": "critical"})

    dup_pub = int(counters.get("duplicate_publish_total", 0))
    if dup_pub > 0:
        alerts.append({"kind": "duplicate_publish", "severity": "warning"})

    zero_ticks = int(counters.get("pipeline_zero_output_ticks", 0))
    if zero_ticks >= 3:
        alerts.append({"kind": "silent_pipeline_degradation", "severity": "warning"})

    topic_spike = int(counters.get("topic_spike_total", 0))
    if topic_spike > 5:
        alerts.append({"kind": "unusual_topic_spike", "severity": "notice"})

    try:
        from app.editorial.feedback_loop import feedback_summary

        fb = feedback_summary(runtime_dir=runtime_dir)
        if fb.get("manual_reject", 0) > 5 and pub_ok < 3:
            alerts.append({"kind": "high_reject_low_publish", "severity": "warning"})
    except Exception:
        pass

    return {
        "ts": time.time(),
        "alert_count": len(alerts),
        "alerts": alerts,
        "healthy": len([a for a in alerts if a.get("severity") == "critical"]) == 0,
    }
