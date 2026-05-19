#!/usr/bin/env python3
"""Record one operational observation pulse (30–60 min cadence during 48h phase)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_observation.baseline import update_baseline
from bot.ops_observation.collector import collect_observation_pulse
from bot.ops_observation.store import OpsObservationStore


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="48h observation pulse")
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--json", action="store_true", help="Print full JSON only")
    p.add_argument("--quiet", action="store_true", help="Suppress human summary")
    args = p.parse_args()

    pulse = collect_observation_pulse(base_url=args.base_url)
    store = OpsObservationStore()
    path = store.append_pulse(pulse)
    baseline = update_baseline(store.load_baseline(), pulse)
    store.save_baseline(baseline)

    if args.json:
        print(json.dumps(pulse, indent=2, default=str))
        return 0 if pulse.get("severity") != "critical" else 2

    if not args.quiet:
        print("=" * 56)
        print(f" OPS OBSERVATION PULSE — {pulse.get('timestamp', '')[:19]}Z")
        print("=" * 56)
        print(f"  instance: {pulse.get('runtime_instance_id')} (pid={pulse.get('pid')})")
        print(f"  profile:  {pulse.get('runtime_profile')}")
        print(f"  live:     mode={pulse.get('live_mode')} frozen={pulse.get('frozen')}")
        print(
            f"  canary:   publishes_this_hour={pulse.get('publishes_this_hour')} "
            f"(cap=3)",
        )
        print(f"  lag:      max={pulse.get('event_loop_lag_max')} avg={pulse.get('event_loop_lag_avg')}")
        print(f"  stalled:  {pulse.get('stalled_loops') or 'none'}")
        print(
            f"  recovery: attempts={pulse.get('recovery_attempt_count')} "
            f"suppressed={pulse.get('recovery_suppressed_count')}",
        )
        ps = pulse.get("publish_stats_24h") or {}
        print(f"  24h:      published={ps.get('published_24h')} held={ps.get('held_24h')}")
        print(f"  severity: {pulse.get('severity', 'ok').upper()}")
        if pulse.get("anomalies"):
            print("\n  ANOMALIES:")
            for a in pulse["anomalies"]:
                print(f"    [{a.get('level')}] {a.get('code')}: {a.get('detail')}")
                if a.get("action"):
                    print(f"      → {a['action']}")
        print(f"\n  saved: {path}")
        print(f"  baseline pulses: {baseline.get('pulse_count')}")
        print("=" * 56)

    sev = pulse.get("severity", "ok")
    if sev == "critical":
        print("ACTION: /freeze_publishing — then inspect traces and logs", file=sys.stderr)
        return 2
    if sev == "warning":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
