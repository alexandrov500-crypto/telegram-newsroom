from __future__ import annotations

from observability.canonical_metrics import ALL_CANONICAL, audit_exported_metrics


def test_canonical_audit_does_not_crash() -> None:
    audit = audit_exported_metrics({"gauges": {"queue_depth": 1}, "counters": {}, "histograms": {}})
    assert "non_canonical_gauges" in audit


def test_canonical_set_nonempty() -> None:
    assert "queue_depth" in ALL_CANONICAL
