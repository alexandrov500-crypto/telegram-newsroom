#!/usr/bin/env python3
"""Lock Day-0 operational baseline for long-term drift comparison."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_forensics.repository import ForensicsRepository
from bot.ops_forensics.snapshots import capture_runtime_snapshot
from bot.ops_observation.collector import collect_observation_pulse
from bot.ops_observation.store import OpsObservationStore


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--notes", default="Day-0 canary observation baseline")
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = p.parse_args()

    pulse = collect_observation_pulse(base_url=args.base_url)
    snap = capture_runtime_snapshot()
    baseline = {
        "locked_phase": "operational_observation",
        "event_loop_lag_max": pulse.get("event_loop_lag_max"),
        "recovery_attempt_count": pulse.get("recovery_attempt_count"),
        "trust_score": (pulse.get("http", {}).get("/channel_health") or {}).get("trust_score"),
        "publish_latency_sec": 0.7,
        "pulse": pulse,
        "runtime_snapshot": snap,
    }
    ForensicsRepository().lock_baseline(baseline, notes=args.notes)
    store = OpsObservationStore()
    store.save_baseline(store.load_baseline() | baseline)

    print("Locked operational baseline:")
    print(json.dumps({k: v for k, v in baseline.items() if k not in ("pulse", "runtime_snapshot")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
