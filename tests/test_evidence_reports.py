from __future__ import annotations

import json

from utils.evidence_reports import build_failure_report, build_recovery_report, build_runtime_stability_report, build_soak_report


def test_evidence_reports_json_roundtrip_keys() -> None:
    soak = {"profile": "low", "ticks": 3, "duration_sec": 0.1, "bounded_report": {"ok": True}, "warnings": []}
    assert "profile" in json.loads(build_soak_report(soak, format="json"))
    assert "<html" in build_soak_report(soak, format="html").lower()
    fail = {"case": "redis", "outcome": "degraded"}
    assert json.loads(build_failure_report(fail, format="json"))["case"] == "redis"
    rec = {"step": "dlq_replay", "ok": True}
    assert "step" in json.loads(build_recovery_report(rec, format="json"))
    stab = {"rss_bytes": 1, "derived": {}}
    assert "rss_bytes" in json.loads(build_runtime_stability_report(stab, format="json"))
