#!/usr/bin/env python3
"""Daily operational snapshot for 48h observation phase."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_observation.collector import collect_observation_pulse
from bot.ops_observation.store import OpsObservationStore
from bot.storage.db import default_db_path, init_database


def _pulse_summary(store: OpsObservationStore, day: str) -> dict:
    path = store.pulses_dir / f"{day}.jsonl"
    if not path.is_file():
        return {"pulse_count": 0}
    severities: dict[str, int] = {}
    lag_max = 0.0
    anomaly_count = 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            continue
        count += 1
        sev = str(p.get("severity", "ok"))
        severities[sev] = severities.get(sev, 0) + 1
        lag_max = max(lag_max, float(p.get("event_loop_lag_max") or 0))
        anomaly_count += len(p.get("anomalies") or [])
    return {
        "pulse_count": count,
        "severity_counts": severities,
        "runtime_lag_max_observed": round(lag_max, 4),
        "anomaly_signals": anomaly_count,
    }


def _daily_db_stats(db_path: Path) -> dict:
    init_database(db_path)
    out: dict = {
        "publishes_count_24h": 0,
        "publish_success_rate": None,
        "source_breakdown": {},
        "operator_feedback": {"good": 0, "bad": 0},
        "major_incidents": [],
    }
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        traces = conn.execute(
            """
            SELECT trace_json FROM live_publish_trace
            WHERE created_at >= datetime('now', '-24 hours')
            """,
        ).fetchall()
        published = 0
        total = len(traces)
        for row in traces:
            try:
                t = json.loads(row["trace_json"] or "{}")
            except json.JSONDecodeError:
                continue
            src = str(t.get("source") or "unknown")
            box = out["source_breakdown"].setdefault(src, {"published": 0, "total": 0})
            box["total"] += 1
            if t.get("published"):
                published += 1
                box["published"] += 1
        out["publishes_count_24h"] = published
        if total:
            out["publish_success_rate"] = round(published / total, 3)

        for row in conn.execute(
            """
            SELECT rating, COUNT(*) AS c FROM live_channel_post_ratings
            WHERE created_at >= datetime('now', '-24 hours')
            GROUP BY rating
            """,
        ):
            out["operator_feedback"][str(row["rating"])] = int(row["c"])

        try:
            inc = conn.execute(
                """
                SELECT title, severity, created_at FROM live_channel_incidents
                WHERE created_at >= datetime('now', '-24 hours')
                ORDER BY created_at DESC LIMIT 10
                """,
            ).fetchall()
            out["major_incidents"] = [
                {"title": r["title"], "severity": r["severity"], "at": r["created_at"]}
                for r in inc
            ]
        except sqlite3.OperationalError:
            pass

    return out


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    store = OpsObservationStore()
    pulse = collect_observation_pulse(base_url=args.base_url)
    db_path = default_db_path()

    snapshot = {
        "date": day,
        "timestamp": now.isoformat(),
        "phase": "operational_observation_48h",
        "publishes_count": pulse.get("publish_stats_24h", {}).get("published_24h"),
        "publish_success_rate": None,
        "runtime_lag_max": pulse.get("event_loop_lag_max"),
        "recovery_count": pulse.get("recovery_attempt_count"),
        "stalled_loop_count": len(pulse.get("stalled_loops") or []),
        "runtime_instance_id": pulse.get("runtime_instance_id"),
        "runtime_profile": pulse.get("runtime_profile"),
        "live_mode": pulse.get("live_mode"),
        "publishes_this_hour": pulse.get("publishes_this_hour"),
        "operator_feedback_summary": pulse.get("publish_stats_24h", {}).get("ratings"),
        "source_quality_notes": _daily_db_stats(db_path).get("source_breakdown"),
        "major_incidents": _daily_db_stats(db_path).get("major_incidents"),
        "pulse_summary": _pulse_summary(store, day),
        "baseline": store.load_baseline(),
        "constraints": {
            "LIVE_MODE": "canary",
            "LIVE_CANARY_MAX_PER_HOUR": 3,
            "RUNTIME_PROFILE": "minimal_pilot",
            "LIVE_SUPERVISED_APPROVAL": True,
        },
        "exit_criteria_reminder": [
            "multiple days without runtime instability",
            "no stalled loops",
            "low consistent event loop lag",
            "stable publish latency",
            "no catastrophic formatting failures",
            "no recovery storms",
            "healthy operator workflow",
        ],
    }
    db = _daily_db_stats(db_path)
    snapshot["publish_success_rate"] = db.get("publish_success_rate")
    snapshot["publishes_count"] = db.get("publishes_count_24h")

    try:
        from bot.editorial.quality.service import (
            build_daily_editorial_snapshot,
            get_editorial_quality_repo,
        )

        eq_repo = get_editorial_quality_repo(db_path)
        editorial = build_daily_editorial_snapshot(eq_repo, day=day, hours=24)
        eq_repo.save_daily_snapshot(day, editorial)
        snapshot["editorial_quality"] = editorial
    except Exception:
        snapshot["editorial_quality"] = {"error": "unavailable"}

    out_path = store.save_daily(snapshot)

    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        print("=" * 56)
        print(f" DAILY OPERATIONAL SNAPSHOT — {day}")
        print("=" * 56)
        print(f"  publishes (24h):        {snapshot.get('publishes_count')}")
        print(f"  publish_success_rate:   {snapshot.get('publish_success_rate')}")
        print(f"  runtime_lag_max:        {snapshot.get('runtime_lag_max')}")
        print(f"  recovery_count:         {snapshot.get('recovery_count')}")
        print(f"  stalled_loop_count:     {snapshot.get('stalled_loop_count')}")
        print(f"  operator_feedback:      {snapshot.get('operator_feedback_summary')}")
        print(f"  source_breakdown:       {json.dumps(snapshot.get('source_quality_notes'))}")
        print(f"  pulses today:           {snapshot.get('pulse_summary')}")
        print(f"  major_incidents:        {len(snapshot.get('major_incidents') or [])}")
        eq = snapshot.get("editorial_quality") or {}
        print(f"  editorial_avg_score:    {eq.get('avg_editorial_quality_score')}")
        print(f"  editorial_posts_scored: {eq.get('count')}")
        print(f"\n  saved: {out_path}")
        print("=" * 56)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
