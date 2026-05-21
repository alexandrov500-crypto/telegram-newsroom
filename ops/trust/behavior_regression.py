"""Deterministic replay-based behavioral regression (offline-safe)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.trust.paths import regression_baseline_path, regression_report_path


def _stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _diff_dict(baseline: Any, current: Any, *, path: str = "") -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    if type(baseline) != type(current):
        diffs.append({"path": path, "baseline": baseline, "current": current, "kind": "type_change"})
        return diffs
    if isinstance(baseline, dict) and isinstance(current, dict):
        keys = sorted(set(baseline) | set(current))
        for k in keys:
            p = f"{path}.{k}" if path else k
            if k not in baseline:
                diffs.append({"path": p, "kind": "added", "current": current[k]})
            elif k not in current:
                diffs.append({"path": p, "kind": "removed", "baseline": baseline[k]})
            else:
                diffs.extend(_diff_dict(baseline[k], current[k], path=p))
        return diffs
    if isinstance(baseline, list) and isinstance(current, list):
        if _stable_hash(baseline) != _stable_hash(current):
            diffs.append({
                "path": path,
                "kind": "list_change",
                "baseline_len": len(baseline),
                "current_len": len(current),
                "baseline_hash": _stable_hash(baseline),
                "current_hash": _stable_hash(current),
            })
        return diffs
    if baseline != current:
        diffs.append({"path": path, "kind": "value_change", "baseline": baseline, "current": current})
    return diffs


def _collect_behavior_snapshot(runtime_dir: str, *, window_hours: float) -> dict[str, Any]:
    since = time.time() - window_hours * 3600.0
    from editorial.governance.ledger import query_decisions
    from editorial.governance.ranking import get_last_ranking_snapshot
    from editorial.governance.policies_engine import load_governance_rules
    from editorial.governance.diversity_controls import diversity_metrics
    from editorial.governance.drift import compute_drift_signals
    from ops.resilience.publish_journal import journal_tail

    decisions = query_decisions(runtime_dir, limit=200)
    in_window = [d for d in decisions if float(d.get("ts_unix") or 0) >= since]
    ranking = get_last_ranking_snapshot(runtime_dir)
    ranked = ranking.get("ranked") or []
    ranking_fp_order = [r.get("fingerprint") for r in ranked if isinstance(r, dict)]
    suppress_outcomes = [d.get("outcome") for d in in_window if "suppress" in str(d.get("decision_type") or "")]
    publish_rows = [j for j in journal_tail(runtime_dir, limit=100) if float(j.get("ts_unix") or 0) >= since]
    drift = compute_drift_signals(runtime_dir)
    div = diversity_metrics(runtime_dir)
    return {
        "window_hours": window_hours,
        "ranking_fingerprint_order": ranking_fp_order[:20],
        "ranking_top_score": (ranked[0].get("trace") or {}).get("weighted_total") if ranked else None,
        "governance_decision_count": len(in_window),
        "suppress_count": len(suppress_outcomes),
        "publish_finalized_count": sum(1 for j in publish_rows if j.get("state") == "finalized"),
        "drift_warnings": list(drift.get("warnings") or []),
        "topic_distribution_hash": _stable_hash(div.get("topic_distribution")),
        "rules_hash": _stable_hash(load_governance_rules(runtime_dir).get("rules")),
        "ranking_weights_hash": _stable_hash(ranking.get("weights")),
    }


def run_behavior_regression(
    runtime_dir: str,
    *,
    window_hours: float | None = None,
    save_baseline: bool = False,
    threshold_diffs: int | None = None,
) -> dict[str, Any]:
    wh = float(window_hours or os.getenv("BEHAVIOR_REGRESSION_WINDOW_HOURS", "24"))
    wh = max(1.0, min(wh, 168.0))
    current = _collect_behavior_snapshot(runtime_dir, window_hours=wh)
    baseline_path = regression_baseline_path(runtime_dir)
    baseline = load_json(baseline_path, {}) if baseline_path.is_file() else {}
    if save_baseline or not baseline:
        save_json(baseline_path, {"version": 1, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "snapshot": current})
        baseline = {"snapshot": current}
    base_snap = baseline.get("snapshot") if isinstance(baseline.get("snapshot"), dict) else baseline
    diffs = _diff_dict(base_snap, current)
    max_diffs = int(threshold_diffs or os.getenv("BEHAVIOR_REGRESSION_MAX_DIFFS", "12"))
    passed = len(diffs) <= max_diffs
    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_hours": wh,
        "passed": passed,
        "diff_count": len(diffs),
        "threshold_max_diffs": max_diffs,
        "diffs": diffs[:50],
        "explainable_summary": [f"{d.get('path')}: {d.get('kind')}" for d in diffs[:15]],
        "current_snapshot": current,
        "baseline_captured_at": baseline.get("captured_at"),
    }
    save_json(regression_report_path(runtime_dir), report)
    return report
