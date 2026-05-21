#!/usr/bin/env python3
"""Offline scalability simulation (non-destructive)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _scenario_source_burst(settings: Any) -> dict[str, Any]:
    from ops.economics.throughput import compute_adaptations

    tp = compute_adaptations(settings, settings.runtime_state_dir)
    return {
        "scenario": "10x_source_burst",
        "projected_queue_pressure": min(1.0, float((tp.get("pressure") or {}).get("queue_pressure") or 0) * 10),
        "recommended": "enable_burst_mode + load_shedding",
        "risk": "high",
    }


def _scenario_openai_outage() -> dict[str, Any]:
    from app.openai_circuit import get_openai_circuit

    return {
        "scenario": "prolonged_openai_outage",
        "circuit_open": get_openai_circuit().is_openai_disabled(),
        "recommended": "degraded_mode_collector_only",
        "risk": "medium" if not get_openai_circuit().is_openai_disabled() else "high",
    }


def _scenario_queue_saturation(settings: Any) -> dict[str, Any]:
    max_q = getattr(settings, "job_queue_max_size", 500)
    return {
        "scenario": "queue_saturation",
        "max_queue": max_q,
        "overflow_counter_note": "simulate depth > max",
        "recommended": "throughput poll_interval_multiplier up, replay off",
        "risk": "high",
    }


def _scenario_publish_spike() -> dict[str, Any]:
    from utils.metrics import export_snapshot

    ctr = dict(export_snapshot().get("counters") or {})
    return {
        "scenario": "publish_spikes",
        "current_publishes": int(ctr.get("publishes") or 0),
        "recommended": "cadence_gate + publish_journal idempotency",
        "risk": "low",
    }


def _scenario_incident_storm(runtime_dir: str) -> dict[str, Any]:
    inc = Path(runtime_dir) / "incidents"
    n = len(list(inc.glob("incident_*.tar.gz"))) if inc.is_dir() else 0
    return {
        "scenario": "incident_storm",
        "current_incidents": n,
        "recommended": "retention prune + storage emergency",
        "risk": "medium" if n < 20 else "high",
    }


def run_simulation(settings: Any, out_path: Path) -> dict[str, Any]:
    rd = settings.runtime_state_dir
    scenarios = [
        _scenario_source_burst(settings),
        _scenario_openai_outage(),
        _scenario_queue_saturation(settings),
        _scenario_publish_spike(),
        _scenario_incident_storm(rd),
    ]
    risks = [s.get("risk") for s in scenarios]
    overall = "high" if "high" in risks else ("medium" if "medium" in risks else "low")
    report = {
        "simulation_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "destructive": False,
        "scenarios": scenarios,
        "overall_risk": overall,
        "limits_observable": {
            "ai_max_tokens_per_hour": __import__("os").environ.get("AI_MAX_TOKENS_PER_HOUR", "120000"),
            "storage_quota_bytes": __import__("os").environ.get("RUNTIME_STORAGE_QUOTA_BYTES", "2000000000"),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    from app.config import load_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="")
    args = parser.parse_args()
    settings = load_settings()
    out = Path(args.output) if args.output else Path(settings.runtime_state_dir) / "scalability_report.json"
    report = run_simulation(settings, out)
    print(json.dumps({"path": str(out), "overall_risk": report["overall_risk"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
