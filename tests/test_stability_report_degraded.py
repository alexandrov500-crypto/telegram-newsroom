from __future__ import annotations

import json

from utils.evidence_reports import build_runtime_stability_report


def test_runtime_stability_report_with_transport_error_still_serializes() -> None:
    payload = {
        "derived": {},
        "transport_sample": {"ok": False, "error": "RuntimeError('simulated')"},
    }
    raw = build_runtime_stability_report(payload, format="json")
    assert json.loads(raw)["transport_sample"]["ok"] is False
