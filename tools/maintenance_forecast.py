#!/usr/bin/env python3
"""Advisory maintenance forecast (read-only; no automatic actions)."""

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


def build_forecast(ctx: dict[str, Any]) -> dict[str, Any]:
    cur = ctx["current"]
    trends = ctx["trends"]
    recovery = ctx["recovery"]
    t = trends.get("trends") or {}
    wal_dir = (t.get("wal_growth") or {}).get("direction")
    ev_dir = (t.get("evidence_growth") or {}).get("direction")
    retry_dir = (t.get("retry_frequency") or {}).get("direction")

    storm_n = int(os.environ.get("RUNTIME_RETRY_STORM_COUNT", "40"))
    retry_ratio = cur.retry_burst_window / max(1, storm_n)

    forecasts: list[dict[str, str]] = []

    if cur.wal_bytes > 32_000_000 or wal_dir == "rising":
        days = 7 if cur.wal_bytes < 128_000_000 else 2
        forecasts.append(
            {
                "area": "wal_checkpoint",
                "urgency": "soon" if days <= 3 else "planned",
                "advisory": f"Recommend quiesced WAL checkpoint within ~{days} days",
                "confidence": str(trends.get("confidence", "low")),
            }
        )

    if cur.evidence_dir_bytes > 100_000_000 or ev_dir == "rising":
        forecasts.append(
            {
                "area": "evidence_prune",
                "urgency": "soon" if cur.evidence_dir_bytes > 400_000_000 else "planned",
                "advisory": "Schedule evidence_retention prune; review OUTPUT_DIR growth",
                "confidence": str(trends.get("confidence", "low")),
            }
        )

    snap = "daily" if cur.evidence_dir_bytes < 200_000_000 else "after_each_nightly"
    forecasts.append(
        {
            "area": "snapshot_cadence",
            "urgency": "routine",
            "advisory": f"Suggested snapshot cadence: {snap}",
            "confidence": "high",
        }
    )

    if retry_ratio >= 0.75:
        forecasts.append(
            {
                "area": "retry_saturation",
                "urgency": "immediate",
                "advisory": "Retry saturation risk elevated — do not scale workers",
                "confidence": "high",
            }
        )

    ev_rate = (t.get("evidence_growth") or {}).get("per_day_delta", 0)
    if ev_rate > 0:
        days_to_500mb = max(1, int((500_000_000 - cur.evidence_dir_bytes) / max(ev_rate, 1)))
        forecasts.append(
            {
                "area": "output_dir_projection",
                "urgency": "planned",
                "advisory": f"At current trend, ~{days_to_500mb} days to 500MB OUTPUT_DIR heuristic",
                "confidence": "medium" if trends.get("sample_count", 0) >= 3 else "low",
            }
        )

    restore_sec = float(recovery.get("restore_duration_estimate_sec") or 0)
    if restore_sec > 15 or (t.get("restore_duration") or {}).get("direction") == "rising":
        forecasts.append(
            {
                "area": "restore_duration",
                "urgency": "planned",
                "advisory": f"Restore drill recommended (estimate {restore_sec}s copy-only)",
                "confidence": "medium",
            }
        )

    if cur.redis_reconnect_count > 3:
        forecasts.append(
            {
                "area": "redis_instability",
                "urgency": "soon",
                "advisory": "Redis reconnect/transport errors trending — stabilize before multi-worker",
                "confidence": "medium",
            }
        )

    return {
        "schema_version": 1,
        "read_only": True,
        "advisory_only": True,
        "forecasts": forecasts[:12],
        "trend_confidence": trends.get("confidence"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", ""))
    p.add_argument("--history-dir", default=os.environ.get("OPS_HISTORY_DIR", "var/ops_history"))
    p.add_argument("--json-output", default="")
    args = p.parse_args()
    od = Path(args.output_dir) if args.output_dir else None
    hd = Path(args.history_dir) if args.history_dir else None
    ctx = build_intel_context(output_dir=od, history_dir=hd)
    report = build_forecast(ctx)
    report["current_sample"] = ctx["current"].to_dict()
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
