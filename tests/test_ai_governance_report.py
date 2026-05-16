from __future__ import annotations

from tests.conftest import minimal_test_settings
from utils.runtime_reports import build_ai_governance_report


def test_ai_governance_report_shape() -> None:
    s = minimal_test_settings()
    r = build_ai_governance_report(s)
    assert r["report"] == "ai_governance"
    assert "counters" in r
    assert "ai_cluster_calls" in r["counters"]
