#!/usr/bin/env python3
"""7-day public launch burn-in GO/NO-GO report from DB + staging health."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _db_connect() -> sqlite3.Connection | None:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path:
        return None
    try:
        return sqlite3.connect(path, timeout=3.0)
    except sqlite3.Error:
        return None


def aggregate_7d_metrics() -> dict[str, object]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    out: dict[str, object] = {"window_days": 7, "since": since}
    conn = _db_connect()
    if conn is None:
        out["db_available"] = False
        return out
    out["db_available"] = True
    try:
        pub = conn.execute(
            """
            SELECT COUNT(*) FROM published_posts pp
            JOIN drafts d ON d.id = pp.draft_id
            WHERE pp.published_at >= ?
            """,
            (since,),
        ).fetchone()
        fail = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status='failed' AND created_at >= ?",
            (since,),
        ).fetchone()
        pend = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status='pending'",
        ).fetchone()
        ticks = conn.execute(
            """
            SELECT status, COUNT(*) FROM pipeline_ticks
            WHERE started_at >= ?
            GROUP BY status
            """,
            (since,),
        ).fetchall()
        out["published_7d"] = int(pub[0] or 0) if pub else 0
        out["failed_drafts_7d"] = int(fail[0] or 0) if fail else 0
        out["pending_now"] = int(pend[0] or 0) if pend else 0
        out["pipeline_ticks_7d"] = {str(r[0]): int(r[1]) for r in ticks}
    finally:
        conn.close()

    try:
        from app.observability.staging_health import staging_health_snapshot

        out["staging_health"] = staging_health_snapshot()
    except Exception as exc:
        out["staging_health_error"] = str(exc)

    return out


def go_no_go(metrics: dict[str, object], *, strict: bool) -> tuple[str, list[str]]:
    issues: list[str] = []
    if not metrics.get("db_available"):
        issues.append("database_unavailable")
    published = int(metrics.get("published_7d") or 0)
    failed = int(metrics.get("failed_drafts_7d") or 0)
    if published == 0 and strict:
        issues.append("zero_publishes_7d")
    if failed > max(5, published // 2) and published > 0:
        issues.append("high_failure_ratio")
    health = metrics.get("staging_health")
    if isinstance(health, dict):
        alerts = health.get("alerts") or []
        critical = [a for a in alerts if isinstance(a, str) and "critical" in a.lower()]
        if critical:
            issues.append(f"critical_alerts:{len(critical)}")
    verdict = "NO-GO" if issues else "GO"
    return verdict, issues


def main() -> int:
    p = argparse.ArgumentParser(description="Public launch 7-day burn-in monitor")
    p.add_argument("--strict", action="store_true", help="Fail on zero publishes")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    metrics = aggregate_7d_metrics()
    verdict, issues = go_no_go(metrics, strict=args.strict)
    report = {"verdict": verdict, "issues": issues, "metrics": metrics}

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"PUBLIC LAUNCH BURN-IN: {verdict}")
        if issues:
            print("Issues:")
            for i in issues:
                print(f"  - {i}")
        print(f"Published (7d): {metrics.get('published_7d', 'n/a')}")
        print(f"Failed drafts (7d): {metrics.get('failed_drafts_7d', 'n/a')}")
        print(f"Pending now: {metrics.get('pending_now', 'n/a')}")
    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
