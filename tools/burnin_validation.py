#!/usr/bin/env python3
"""Burn-in observability: finished-tick snapshot + read-only readiness checker."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.observability.burnin_eval import (  # noqa: E402
    build_snapshot,
    evaluate_readiness,
    fetch_active_ticks,
    fetch_finished_ticks,
    fetch_tail_streak_rows,
    finished_metrics,
    scan_log_contract,
    tail_consecutive_finished_streak,
)
from utils.database_url import sqlite_path_from_url  # noqa: E402


def _db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path:
        raise SystemExit("DATABASE_URL is not a local SQLite path")
    return Path(path)


def _connect(db: Path) -> sqlite3.Connection:
    if not db.is_file():
        raise SystemExit(f"Database not found: {db}")
    return sqlite3.connect(db, timeout=5.0)


def _default_log() -> Path:
    return REPO / "logs" / "local-run.log"


def cmd_snapshot(args: argparse.Namespace) -> int:
    conn = _connect(_db_path(args.db))
    try:
        snap = build_snapshot(
            conn,
            finished_limit=args.limit,
            log_path=Path(args.log) if args.log else _default_log(),
            since_id=args.since_id,
        )
    finally:
        conn.close()

    if args.json:
        out_path = Path(args.write_json) if args.write_json else None
        payload = json.dumps(snap, indent=2, ensure_ascii=False, default=str)
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload + "\n", encoding="utf-8")
            print(f"Wrote {out_path}")
        print(payload)
        return 0

    print("=== BURN-IN SNAPSHOT (finished ticks only in metrics) ===")
    if snap.get("since_id") is not None:
        print(f"Since tick id: {snap['since_id']} (post-deploy window)")
    print(f"Verdict: {snap['verdict']}")
    if snap["readiness_reasons"]:
        print("Reasons:")
        for r in snap["readiness_reasons"]:
            print(f"  - {r}")
    print(f"Tail consecutive finished (from highest id): {snap['tail_consecutive_finished_count']}")
    m = snap["finished_metrics"]
    print(
        f"Finished window: count={m['count']} ok={m['ok']} reject={m['reject']} "
        f"reject_rate={m['reject_rate']} avg_duration_ms={m['avg_duration_ms']}"
    )
    pm = snap.get("publishability_metrics") or {}
    if pm:
        print(
            f"Publishability: running={pm.get('running_ticks')} "
            f"draft_24h={pm.get('committed_draft_24h')} "
            f"draft_rate={pm.get('draft_rate')} reject_rate={pm.get('reject_rate')}"
        )
    print(
        f"Terminal: draft={m['committed_draft']} reject={m['committed_reject']} "
        f"idle={m['committed_idle']} missing={m['missing_terminal_state']}"
    )
    re_m = snap.get("resolver_era_metrics") or {}
    if re_m.get("count"):
        print(
            f"Resolver-era finished only: count={re_m['count']} ok={re_m['ok']} reject={re_m['reject']} "
            f"missing_terminal={re_m['missing_terminal_state']}"
        )
    lc = snap["log_contract"]
    print(
        f"Log contract ({lc.get('log_path', 'n/a')}): "
        f"aborted_draft={lc.get('aborted_draft', '?')} "
        f"PIPELINE_FATAL_BREAK={lc.get('pipeline_fatal_break', '?')}"
    )
    if lc.get("available"):
        print(
            f"Log signals: terminal_state={lc.get('pipeline_terminal_state', 0)} "
            f"summarize_exit_reject={lc.get('summarize_exit_reject', 0)} "
            f"openai_failed={lc.get('openai_summarize_failed', 0)} "
            f"openai_429≈{lc.get('openai_429', 0)} "
            f"fallback={lc.get('rule_fallback', 0)} "
            f"collect_timeout={lc.get('collect_cycle_timeout', 0)}"
        )

    print("\n--- ACTIVE / IN-FLIGHT (excluded from metrics) ---")
    hb = snap.get("head_in_flight_blocker")
    if hb:
        print(f"  HEAD BLOCKER (streak gap): id={hb['id']} status={hb['status']} age_sec={hb.get('running_age_sec')}")
    for a in snap["active_ticks"]:
        tag = " [head]" if hb and a.get("id") == hb.get("id") else ""
        age = a.get("running_age_sec")
        age_s = f" age_sec={age}" if age is not None else ""
        print(f"  id={a['id']} status={a['status']} tick_id={a['tick_id']}{age_s}{tag}")
    orphans = snap.get("orphan_active_ticks") or []
    if orphans:
        print(f"  (orphan running rows for DB cleanup: {len(orphans)})")

    print("\n--- FINISHED TICKS (newest first) ---")
    print(f"{'id':>4}  {'status':<8}  {'terminal_state':<18}  {'draft':>5}  finished_at")
    for t in snap["finished_ticks"]:
        print(
            f"{t['id']:>4}  {t['status']:<8}  {t['terminal_state'] or '(missing)':<18}  "
            f"{str(t['draft_id'] or '-'):>5}  {t['finished_at']}"
        )

    print("\n--- TAIL STREAK (consecutive finished from highest id) ---")
    for t in snap["tail_streak_finished"]:
        reason = (t.get("terminal_reason") or "")[:60]
        print(
            f"  id={t['id']} {t['status']} {t['terminal_state']} "
            f"draft_id={t['draft_id']} reason={reason!r}"
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    conn = _connect(_db_path(args.db))
    log_path = Path(args.log) if args.log else _default_log()
    try:
        tail = fetch_tail_streak_rows(conn, max_rows=args.limit, since_id=args.since_id)
        if args.since_id is not None:
            ids = conn.execute(
                """
                SELECT id, finished_at FROM pipeline_ticks
                WHERE id >= ?
                ORDER BY id DESC LIMIT ?
                """,
                (args.since_id, args.limit),
            ).fetchall()
        else:
            ids = conn.execute(
                "SELECT id, finished_at FROM pipeline_ticks ORDER BY id DESC LIMIT ?",
                (args.limit,),
            ).fetchall()
        streak = tail_consecutive_finished_streak([(int(i), f) for i, f in ids])
        log_scan = scan_log_contract(log_path)
        from app.observability.burnin_eval import active_stuck_warnings, fetch_active_ticks, fetch_head_in_flight_blocker

        active = fetch_active_ticks(conn, limit=args.limit)
        head_blocker = fetch_head_in_flight_blocker(conn)
        verdict, reasons = evaluate_readiness(
            tail_streak=tail,
            streak_count=streak,
            log_scan=log_scan,
            min_ticks=args.min_ticks,
            max_ticks=args.max_ticks,
            require_golden=args.require_golden,
            active_warnings=active_stuck_warnings(active, head_blocker=head_blocker),
        )
    finally:
        conn.close()

    if args.json:
        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "reasons": reasons,
                    "tail_consecutive_finished": streak,
                    "log_contract": log_scan,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"BURN-IN READINESS: {verdict}")
        if reasons:
            print("Reasons:")
            for r in reasons:
                print(f"  - {r}")
        else:
            print("All checks passed for tail finished streak and log contract.")
        print(f"Consecutive finished ticks (tail): {streak} (min required: {args.min_ticks})")
    return 0 if verdict == "PASS" else (1 if verdict == "FAIL" else 2)


def cmd_sql(args: argparse.Namespace) -> int:
    """Print ready-to-run SQL for operators."""
    queries = {
        "finished": """
SELECT id, tick_id, status,
       json_extract(detail_json, '$.terminal_state') AS terminal_state,
       json_extract(detail_json, '$.draft_id') AS draft_id,
       datetime(finished_at) AS finished_at
FROM pipeline_ticks
WHERE finished_at IS NOT NULL
ORDER BY id DESC
LIMIT 20;
""".strip(),
        "active": """
SELECT id, tick_id, status, datetime(started_at) AS started_at
FROM pipeline_ticks
WHERE finished_at IS NULL
ORDER BY id DESC;
""".strip(),
    }
    key = args.which
    print(queries[key])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Burn-in validation (read-only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("snapshot", help="Finished vs active ticks + metrics")
    ps.add_argument("--db", help="SQLite path (default: DATABASE_URL)")
    ps.add_argument("--log", help="Log file for contract scan")
    ps.add_argument("--limit", type=int, default=15, help="Rows per section")
    ps.add_argument(
        "--since-id",
        type=int,
        default=None,
        help="Only ticks with id >= N (post-deploy / post-restart window)",
    )
    ps.add_argument("--json", action="store_true")
    ps.add_argument(
        "--write-json",
        metavar="PATH",
        help="Also write snapshot JSON (e.g. var/runtime/burnin_snapshot.json)",
    )
    ps.set_defaults(func=cmd_snapshot)

    pc = sub.add_parser("check", help="PASS / CONDITIONAL / FAIL readiness")
    pc.add_argument("--db")
    pc.add_argument("--log")
    pc.add_argument("--min-ticks", type=int, default=3)
    pc.add_argument("--max-ticks", type=int, default=7)
    pc.add_argument("--require-golden", action="store_true")
    pc.add_argument("--limit", type=int, default=15)
    pc.add_argument(
        "--since-id",
        type=int,
        default=None,
        help="Only ticks with id >= N (post-deploy window)",
    )
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(func=cmd_check)

    pq = sub.add_parser("sql", help="Print SQL helpers")
    pq.add_argument("which", choices=("finished", "active"))
    pq.set_defaults(func=cmd_sql)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
