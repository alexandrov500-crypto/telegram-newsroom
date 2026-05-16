#!/usr/bin/env python3
"""Deterministic drift / pressure risk forecast (explainable heuristics)."""

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

from utils.operational_intel_context import build_intel_context


def _risk(score: int, *, reason: str) -> dict[str, Any]:
    level = "low"
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    return {"score": min(100, score), "level": level, "reason": reason}


def build_drift_forecast(ctx: dict[str, Any]) -> dict[str, Any]:
    cur = ctx["current"]
    trends = ctx["trends"]
    t = trends.get("trends") or {}
    storm_n = int(os.environ.get("RUNTIME_RETRY_STORM_COUNT", "40"))

    retention_score = 0
    if cur.evidence_dir_bytes > 400_000_000:
        retention_score += 50
    if (t.get("evidence_growth") or {}).get("direction") == "rising":
        retention_score += 30
    retention_score += min(20, int(cur.drift_finding_count) * 5)

    wal_score = 0
    if cur.wal_bytes > 268_435_456:
        wal_score = 80
    elif cur.wal_bytes > 64_000_000:
        wal_score = 45
    if (t.get("wal_growth") or {}).get("direction") == "rising":
        wal_score = min(100, wal_score + 25)

    queue_score = min(100, int(cur.queue_pending) * 2)
    retry_prob = min(100, int(100 * cur.retry_burst_window / max(1, storm_n)))
    if (t.get("retry_frequency") or {}).get("direction") == "rising":
        retry_prob = min(100, retry_prob + 20)

    evidence_pressure = min(100, int(cur.evidence_dir_bytes / 5_000_000))
    sched_score = min(100, cur.scheduler_overlap_total * 25 + int(cur.scheduler_max_lag_sec * 10))

    risks = {
        "retention_exhaustion": _risk(retention_score, reason="OUTPUT_DIR / drift trend"),
        "wal_pressure": _risk(wal_score, reason="WAL size and growth"),
        "queue_saturation": _risk(queue_score, reason="pending queue depth"),
        "retry_storm_probability": _risk(retry_prob, reason="retry burst vs storm threshold"),
        "evidence_storage_pressure": _risk(evidence_pressure, reason="evidence bytes heuristic"),
        "scheduler_drift_escalation": _risk(sched_score, reason="overlap and lag"),
    }
    explain = [f"{k}: {v['level']} ({v['score']}) — {v['reason']}" for k, v in risks.items()]
    return {
        "schema_version": 1,
        "read_only": True,
        "advisory_only": True,
        "risks": risks,
        "explanations": explain,
        "confidence_limit": "Heuristic only; not probabilistic ML",
        "sample_count": trends.get("sample_count", 0),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", ""))
    p.add_argument("--history-dir", default=os.environ.get("OPS_HISTORY_DIR", "var/ops_history"))
    p.add_argument("--json-output", default="")
    args = p.parse_args()
    od = Path(args.output_dir) if args.output_dir else None
    hd = Path(args.history_dir) if args.history_dir else None
    report = build_drift_forecast(build_intel_context(output_dir=od, history_dir=hd))
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
