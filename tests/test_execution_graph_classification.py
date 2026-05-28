"""Anomaly severity classification."""

from __future__ import annotations

from app.observability.execution_graph_classification import (
    AnomalySeverity,
    classify_anomaly,
    partition_anomalies,
)


def test_critical_vs_warning():
    assert classify_anomaly("duplicate_finalize") == AnomalySeverity.CRITICAL
    assert classify_anomaly("delayed_finalize") == AnomalySeverity.WARNING
    w, c = partition_anomalies(["tick_overlap", "publish_without_gate_allowed"])
    assert "tick_overlap" in w
    assert "publish_without_gate_allowed" in c
