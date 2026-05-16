#!/usr/bin/env python3
"""CLI operational summary (read-only intelligence dashboard)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.drift_forecast import build_drift_forecast
from tools.maintenance_forecast import build_forecast
from tools.maintenance_recommendations import build_recommendations
from utils.operational_intel_context import build_intel_context


def _unsafe_config_hints() -> list[str]:
    hints: list[str] = []
    env = os.environ

    def on(k: str) -> bool:
        return env.get(k, "").strip().lower() in {"1", "true", "yes", "on"}

    if on("REDIS_ENABLED") and not on("PUBLISH_LOCK_STRICT"):
        hints.append("REDIS_ENABLED without PUBLISH_LOCK_STRICT (multi-worker publish risk)")
    if on("REDIS_ENABLED") and not on("WORKER_RETRY_SAFE"):
        hints.append("REDIS_ENABLED without WORKER_RETRY_SAFE (retry safety)")
    if on("PUBLISH_LOCK_STRICT") and not on("REDIS_ENABLED"):
        hints.append("PUBLISH_LOCK_STRICT without REDIS_ENABLED")
    return hints


def _scalability_pressure(drift_fc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key, val in (drift_fc.get("risks") or {}).items():
        if val.get("level") in ("medium", "high"):
            out.append(f"{key}: {val.get('level')}")
    return out[:6]


def build_ops_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    forecast = build_forecast(ctx)
    drift_fc = build_drift_forecast(ctx)
    recs = build_recommendations(ctx)
    unsafe = _unsafe_config_hints()
    try:
        proc = subprocess.run(
            [sys.executable, str(REPO / "tools/scalability_diagnostics.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
        )
        scale = json.loads(proc.stdout) if proc.returncode == 0 else {"status": "unknown"}
    except Exception:
        scale = {"status": "unavailable"}

    return {
        "schema_version": 1,
        "read_only": True,
        "operational_summary": {
            "health_status": recs["health"]["status"],
            "health_score": recs["health"]["health_score"],
            "topology_hint": scale.get("topology_hint"),
            "scalability_status": scale.get("status"),
        },
        "risk_indicators": _scalability_pressure(drift_fc) + [
            f"scalability: {f.get('code')}" for f in (scale.get("findings") or [])[:4]
        ],
        "maintenance_due": (recs.get("daily") or [])[:3] + (recs.get("weekly") or [])[:2],
        "recovery_readiness": recs.get("recovery_readiness_warnings", []),
        "retention_pressure": [
            x for x in (drift_fc.get("explanations") or []) if "retention" in x or "evidence" in x
        ][:3],
        "unsafe_configuration_hints": unsafe,
        "top_forecasts": (forecast.get("forecasts") or [])[:5],
        "confidence_note": "Advisory heuristics only; operator remains responsible",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only operational intelligence summary")
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", ""))
    p.add_argument("--history-dir", default=os.environ.get("OPS_HISTORY_DIR", "var/ops_history"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    od = Path(args.output_dir) if args.output_dir else None
    hd = Path(args.history_dir) if args.history_dir else None
    report = build_ops_summary(build_intel_context(output_dir=od, history_dir=hd))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        s = report["operational_summary"]
        print("=== Operational summary ===")
        print(f"Health: {s['health_status']} (score {s['health_score']})")
        print(f"Topology: {s.get('topology_hint')} | Scalability: {s.get('scalability_status')}")
        print("\n--- Risk indicators ---")
        for r in report.get("risk_indicators") or []:
            print(f"  • {r}")
        print("\n--- Maintenance due ---")
        for m in report.get("maintenance_due") or []:
            print(f"  [{m.get('priority')}] {m.get('text')}")
        print("\n--- Recovery readiness ---")
        for w in report.get("recovery_readiness") or []:
            print(f"  [{w.get('priority')}] {w.get('text')}")
        if report.get("unsafe_configuration_hints"):
            print("\n--- Unsafe configuration hints ---")
            for h in report["unsafe_configuration_hints"]:
                print(f"  ! {h}")
        print(f"\n({report.get('confidence_note')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
