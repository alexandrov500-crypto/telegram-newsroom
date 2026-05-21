#!/usr/bin/env python3
"""Non-destructive recovery drill simulations (writes report only)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _simulate_runtime_crash(runtime_dir: str) -> dict[str, Any]:
    from ops.resilience.publish_journal import find_inflight

    inflight = find_inflight(runtime_dir)
    return {
        "scenario": "runtime_crash",
        "inflight_publishes": len(inflight),
        "recovery_action": "review publish_journal + restart with leadership stale recovery",
        "risk": "low" if not inflight else "medium",
    }


def _simulate_queue_corruption() -> dict[str, Any]:
    return {
        "scenario": "queue_corruption",
        "recovery_action": "flush Redis prefix or restart job queue; no production writes in drill",
        "risk": "simulated_only",
    }


def _simulate_partial_publish(runtime_dir: str) -> dict[str, Any]:
    from ops.resilience.publish_journal import journal_tail

    tail = journal_tail(runtime_dir, limit=20)
    stuck = [r for r in tail if r.get("state") in ("sending", "sent") and not any(
        x.get("draft_id") == r.get("draft_id") and x.get("state") == "finalized" for x in tail
    )]
    return {
        "scenario": "partial_publish_failure",
        "stuck_candidates": len(stuck),
        "recovery_action": "idempotency_key + journal finalize replay; mark_draft_failed if send failed",
        "risk": "medium" if stuck else "low",
    }


def _simulate_stale_leadership(runtime_dir: str) -> dict[str, Any]:
    locks = Path(runtime_dir) / "locks"
    holders = []
    if locks.is_dir():
        for p in locks.glob("*.lock"):
            try:
                holders.append({"lock": p.name, "size": p.stat().st_size})
            except OSError:
                pass
    return {
        "scenario": "stale_leadership_lock",
        "lock_files": holders,
        "recovery_action": "stale PID / TTL recovery on next acquire",
        "risk": "low",
    }


def _simulate_openai_outage() -> dict[str, Any]:
    from app.openai_circuit import get_openai_circuit

    snap = get_openai_circuit().snapshot()
    return {
        "scenario": "openai_outage",
        "circuit": snap,
        "recovery_action": "degraded mode; collector continues; AI steps skip",
        "risk": "low" if not snap.get("open") else "medium",
    }


def _simulate_policy_corruption(runtime_dir: str) -> dict[str, Any]:
    from editorial.intelligence_store import editorial_policies_path

    path = editorial_policies_path(runtime_dir)
    ok = True
    err = ""
    if path.is_file():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            ok = False
            err = str(exc)
    return {
        "scenario": "policy_corruption",
        "policies_valid": ok,
        "error": err[:200],
        "recovery_action": "restore editorial_policies.json from last full_snapshot",
        "risk": "high" if not ok else "low",
    }


def _simulate_replay_corruption(runtime_dir: str) -> dict[str, Any]:
    rt = Path(runtime_dir)
    bad = 0
    for p in rt.glob("snapshot_*.json"):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            bad += 1
    return {
        "scenario": "replay_corruption",
        "invalid_runtime_snapshots": bad,
        "recovery_action": "delete corrupt snapshot_*.json; rely on full_snapshots restore",
        "risk": "medium" if bad else "low",
    }


def run_drill(runtime_dir: str, out_path: Path) -> dict[str, Any]:
    scenarios = [
        _simulate_runtime_crash(runtime_dir),
        _simulate_queue_corruption(),
        _simulate_partial_publish(runtime_dir),
        _simulate_stale_leadership(runtime_dir),
        _simulate_openai_outage(),
        _simulate_policy_corruption(runtime_dir),
        _simulate_replay_corruption(runtime_dir),
    ]
    report = {
        "drill_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_dir": runtime_dir,
        "destructive": False,
        "scenarios": scenarios,
        "overall_risk": (
            "high"
            if any(s.get("risk") == "high" for s in scenarios)
            else ("medium" if any(s.get("risk") == "medium" for s in scenarios) else "low")
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    from app.config import load_settings

    parser = argparse.ArgumentParser(description="Recovery drill (non-destructive)")
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="Report path (default: RUNTIME_STATE_DIR/recovery_drill_report.json)",
    )
    args = parser.parse_args()
    settings = load_settings()
    out = Path(args.output) if args.output else Path(settings.runtime_state_dir) / "recovery_drill_report.json"
    report = run_drill(settings.runtime_state_dir, out)
    print(json.dumps({"report_path": str(out), "overall_risk": report["overall_risk"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
