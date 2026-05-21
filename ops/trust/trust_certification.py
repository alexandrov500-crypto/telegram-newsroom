"""Periodic trust certification artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import save_json
from ops.trust.paths import trust_certification_path


def generate_trust_certification(settings: Any, runtime_dir: str) -> dict[str, Any]:
    from ops.economics.slo import compute_slo_status
    from ops.trust.autonomous_validation import run_autonomous_validation
    from ops.trust.drift_baselines import assess_drift_vs_baseline
    from ops.trust.behavior_regression import run_behavior_regression
    from ops.audit.search import search_audit
    from ops.control.journal import query_control_actions

    slo = compute_slo_status(settings, runtime_dir)
    validation = run_autonomous_validation(settings, runtime_dir)
    drift = assess_drift_vs_baseline(runtime_dir)
    regression = run_behavior_regression(runtime_dir, window_hours=24.0)
    since_7d = time.time() - 7 * 86400.0
    drift_events = search_audit(runtime_dir, entity="drift_warning", since_unix=since_7d, limit=50)
    anomalies = search_audit(runtime_dir, entity="anomaly", since_unix=since_7d, limit=50)
    interventions = query_control_actions(runtime_dir, limit=80)
    drill_path = Path(runtime_dir) / "recovery_drill_report.json"
    drill_ok = True
    if drill_path.is_file():
        try:
            drill = json.loads(drill_path.read_text(encoding="utf-8"))
            drill_ok = drill.get("overall_risk") in ("low", "medium", None)
        except (OSError, json.JSONDecodeError):
            drill_ok = False
    cert = {
        "schema_version": 1,
        "certified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aggregate_trusted": bool(
            slo.get("aggregate_ok")
            and validation.get("passed")
            and regression.get("passed")
            and drift.get("within_baseline", True)
        ),
        "slo_compliance": slo,
        "autonomous_validation": {"passed": validation.get("passed"), "checks": validation.get("checks")},
        "behavior_regression": {"passed": regression.get("passed"), "diff_count": regression.get("diff_count")},
        "replay_integrity": slo.get("slos", {}).get("replay_integrity"),
        "duplicate_prevention": slo.get("slos", {}).get("duplicate_prevention_rate"),
        "governance_explainability": slo.get("slos", {}).get("governance_explainability"),
        "drift_frequency_7d": len(drift_events.get("results") or []),
        "anomaly_rate_7d": len(anomalies.get("results") or []),
        "drift_baseline_assessment": drift,
        "recovery_drill_ok": drill_ok,
        "snapshot_restore_available": slo.get("slos", {}).get("snapshot_restore_available"),
        "operator_intervention_count": len(interventions),
        "operator_interventions_recent": interventions[:10],
    }
    path = trust_certification_path(runtime_dir)
    save_json(path, cert)
    return cert


def latest_trust_certification(runtime_dir: str) -> dict[str, Any]:
    root = Path(runtime_dir).expanduser().resolve() / "trust"
    if not root.is_dir():
        return {}
    files = sorted(root.glob("trust_certification_*.json"), reverse=True)
    if not files:
        return {}
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
