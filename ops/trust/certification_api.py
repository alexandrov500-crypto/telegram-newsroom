"""GET /runtime/certification/* and /runtime/canary/* /runtime/evolution/*"""

from __future__ import annotations

import json
from typing import Any


def _json(obj: Any) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


async def dispatch_trust_runtime_http(
    settings: Any,
    path_only: str,
    *,
    query: dict[str, list[str]] | None = None,
) -> tuple[int, str, bytes] | None:
    rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    p = path_only.rstrip("/")

    if p == "/runtime/certification/trust":
        from ops.trust.trust_certification import latest_trust_certification, generate_trust_certification

        cert = latest_trust_certification(rd)
        if not cert:
            cert = generate_trust_certification(settings, rd)
        return _json(cert)

    if p == "/runtime/certification/regressions":
        from ops.trust.behavior_regression import run_behavior_regression
        from ops.trust.paths import regression_report_path
        from editorial.intelligence_store import load_json

        report = load_json(regression_report_path(rd), {})
        if not report:
            report = run_behavior_regression(rd)
        return _json(report)

    if p == "/runtime/certification/validation":
        from ops.trust.autonomous_validation import run_autonomous_validation
        from ops.trust.paths import validation_report_path
        from editorial.intelligence_store import load_json

        rep = load_json(validation_report_path(rd), {})
        if not rep:
            rep = run_autonomous_validation(settings, rd)
        return _json(rep)

    if p == "/runtime/certification/drift":
        from ops.trust.drift_baselines import assess_drift_vs_baseline

        return _json(assess_drift_vs_baseline(rd))

    if p == "/runtime/canary/status":
        from ops.trust.canary import canary_status_payload

        return _json(canary_status_payload(rd))

    if p == "/runtime/evolution/history":
        from ops.trust.evolution_journal import query_evolution_history

        q = query or {}
        limit = int((q.get("limit") or ["100"])[0])
        et = (q.get("event_type") or [""])[0].strip() or None
        return _json({"entries": query_evolution_history(rd, limit=limit, event_type=et)})

    return None
