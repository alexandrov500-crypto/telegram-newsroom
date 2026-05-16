#!/usr/bin/env python3
"""Operator-readable maintenance recommendations (bounded; advisory)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.drift_forecast import build_drift_forecast
from tools.maintenance_forecast import build_forecast
from utils.operational_intel_context import build_intel_context
from utils.operational_health import compute_health_score


def _rec(priority: str, text: str) -> dict[str, str]:
    return {"priority": priority, "text": text}


def build_recommendations(ctx: dict[str, Any]) -> dict[str, Any]:
    cur = ctx["current"]
    forecast = build_forecast(ctx)
    drift_fc = build_drift_forecast(ctx)
    recovery = ctx["recovery"]
    storm_n = int(os.environ.get("RUNTIME_RETRY_STORM_COUNT", "40"))

    health = compute_health_score(
        retry_burst=cur.retry_burst_window,
        retry_threshold=storm_n,
        wal_bytes=cur.wal_bytes,
        evidence_bytes=cur.evidence_dir_bytes,
        drift_findings=cur.drift_finding_count,
        scheduler_overlap=cur.scheduler_overlap_total,
        backup_risk=str((recovery.get("backup_freshness") or {}).get("risk", "LOW")),
        unsafe_config_count=0,
        trend_anomaly_count=len(ctx["trends"].get("anomalies") or []),
    )

    daily: list[dict[str, str]] = []
    weekly: list[dict[str, str]] = []
    monthly: list[dict[str, str]] = []
    release_cycle: list[dict[str, str]] = []
    recovery_warnings: list[dict[str, str]] = []

    for f in forecast.get("forecasts") or []:
        if f.get("urgency") == "immediate":
            daily.append(_rec("P1", f["advisory"]))
        elif f.get("urgency") == "soon":
            daily.append(_rec("P2", f["advisory"]))
        elif f.get("urgency") == "planned":
            weekly.append(_rec("P3", f["advisory"]))
        else:
            weekly.append(_rec("routine", f["advisory"]))

    for hint in (ctx["trends"].get("maintenance_hints") or [])[:5]:
        weekly.append(_rec("hint", hint))

    monthly.extend(
        [
            _rec("routine", "Run compare-baseline drift check if RUNTIME_DRIFT_MONITOR enabled"),
            _rec("routine", "Review evidence_retention policy vs disk budget"),
            _rec("routine", "SQLite WAL checkpoint after quiesce"),
        ]
    )

    release_cycle.extend(
        [
            _rec("gate", "make release-check before tag"),
            _rec("gate", "make governance-validate + scalability-validate"),
            _rec("gate", "Archive OUTPUT_DIR snapshot for release evidence"),
        ]
    )

    if health["status"] in ("WARNING", "HIGH_RISK"):
        recovery_warnings.append(
            _rec("P1", f"Operational health {health['status']} — run recovery drill before risky changes")
        )
    for w in recovery.get("degraded_recovery_warnings") or []:
        recovery_warnings.append(_rec("P2", w))

    high_risks = [k for k, v in (drift_fc.get("risks") or {}).items() if v.get("level") == "high"]
    if high_risks:
        daily.append(_rec("P1", f"Elevated forecast risks: {', '.join(high_risks[:4])}"))

    return {
        "schema_version": 1,
        "read_only": True,
        "advisory_only": True,
        "health": health,
        "daily": daily[:5],
        "weekly": weekly[:8],
        "monthly": monthly[:6],
        "release_cycle": release_cycle[:6],
        "recovery_readiness_warnings": recovery_warnings[:6],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", ""))
    p.add_argument("--history-dir", default=os.environ.get("OPS_HISTORY_DIR", "var/ops_history"))
    p.add_argument("--json-output", default="")
    args = p.parse_args()
    od = Path(args.output_dir) if args.output_dir else None
    hd = Path(args.history_dir) if args.history_dir else None
    report = build_recommendations(build_intel_context(output_dir=od, history_dir=hd))
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
