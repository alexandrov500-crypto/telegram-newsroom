#!/usr/bin/env python3
"""
Validate upstream draft generation path (raw → cluster → desk → draft).

Usage:
  python3 tools/verify_draft_generation.py
  python3 tools/verify_draft_generation.py --watch-ticks 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv()


def _db_path() -> str | None:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    return sqlite_path_from_url(raw)


def _health() -> dict[str, Any]:
    import urllib.request

    port = int(os.getenv("HEALTH_HTTP_PORT", "8080") or 0)
    if port <= 0:
        return {"error": "HEALTH_HTTP_PORT not set"}
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
        return json.loads(resp.read().decode())


def _tick_drafts_created(conn) -> int:
    row = conn.execute(
        "SELECT drafts_created FROM pipeline_ticks ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row[0]) if row else 0


def verify(*, watch_ticks: int = 0) -> dict[str, Any]:
    import sqlite3

    from app.recovery.pipeline_overrides import (
        is_force_ai_pipeline_enabled,
        is_minimal_pipeline_mode,
        upstream_pipeline_state,
    )

    out: dict[str, Any] = {
        "ok": False,
        "stage_failure": None,
        "checks": {},
    }

    health: dict[str, Any] = {}
    try:
        health = _health()
        out["checks"]["health"] = {
            "ai_pipeline_enabled": health.get("ai_pipeline_enabled"),
            "upstream_pipeline_state": health.get("upstream_pipeline_state"),
            "summarize_idle": (health.get("pipeline") or {}).get("summarize_idle"),
        }
    except Exception as exc:
        out["checks"]["health"] = {"error": repr(exc)}
        out["stage_failure"] = "runtime:health_unreachable"
        return out

    path = _db_path()
    if not path or not Path(path).is_file():
        out["stage_failure"] = "database:missing"
        return out

    conn = sqlite3.connect(path)
    try:
        raw_unprocessed = int(
            conn.execute("SELECT COUNT(*) FROM raw_posts WHERE processed_at IS NULL").fetchone()[0]
        )
        drafts_total = int(conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0])
        baseline_ticks = int(conn.execute("SELECT COUNT(*) FROM pipeline_ticks").fetchone()[0])
        baseline_drafts = drafts_total
        dc_before = _tick_drafts_created(conn)

        out["checks"]["raw_unprocessed"] = raw_unprocessed
        out["checks"]["drafts_total"] = drafts_total
        out["checks"]["last_tick_drafts_created"] = dc_before
        out["checks"]["recovery_flags"] = {
            "FORCE_AI_PIPELINE_ENABLED": is_force_ai_pipeline_enabled(),
            "MINIMAL_PIPELINE_MODE": is_minimal_pipeline_mode(),
        }

        if raw_unprocessed <= 0:
            out["stage_failure"] = "ingestion:no_raw_unprocessed"
            return out

        from app.recovery.pipeline_context_builder import build_pipeline_decision_context
        from app.state.pipeline_decision_engine import make_pipeline_decision

        ctx_eval = build_pipeline_decision_context()
        rec_eval = make_pipeline_decision(ctx_eval)

        class _Rec:
            ai_pipeline_enabled = rec_eval.should_execute
            summarize_enabled = rec_eval.summarize_enabled
            reason = rec_eval.reason
            circuit_state = ctx_eval.circuit_state

        rec = _Rec()
        out["checks"]["reconcile"] = {
            "ai_pipeline_enabled": rec.ai_pipeline_enabled,
            "summarize_enabled": rec.summarize_enabled,
            "reason": rec.reason,
            "circuit_state": rec.circuit_state,
        }
        runtime_ai = bool(health.get("ai_pipeline_enabled"))
        if not rec.ai_pipeline_enabled and not is_force_ai_pipeline_enabled():
            out["stage_failure"] = "upstream:ai_pipeline_disabled"
            return out
        if not runtime_ai and rec.ai_pipeline_enabled:
            out["checks"]["health_stale"] = (
                "running process /health has old code or pre-reconcile state; restart app.main"
            )

        if watch_ticks > 0:
            out["checks"]["watch"] = {"ticks": watch_ticks, "samples": []}
            for _ in range(watch_ticks):
                time.sleep(float(os.getenv("PIPELINE_INTERVAL_MINUTES", "15")) * 60 / 4 or 30)
                dc = _tick_drafts_created(conn)
                drafts_now = int(conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0])
                out["checks"]["watch"]["samples"].append(
                    {"drafts_created_last_tick": dc, "drafts_total": drafts_now}
                )
                if dc > 0 or drafts_now > baseline_drafts:
                    out["ok"] = True
                    out["stage_failure"] = None
                    return out
            out["stage_failure"] = "summarize:no_drafts_created_over_watch_window"
            return out

        if dc_before > 0:
            out["ok"] = True
            return out

        idle = (health.get("pipeline") or {}).get("summarize_idle") or ""
        if idle:
            if idle.startswith("desk_reject"):
                out["stage_failure"] = f"desk:{idle}"
            elif idle.startswith("load_shedding") or idle.startswith("ai_budget"):
                out["stage_failure"] = f"upstream:{idle}"
            elif idle.startswith("cluster") or "cohesion" in idle:
                out["stage_failure"] = f"clustering:{idle}"
            elif "no_unprocessed" in idle:
                out["stage_failure"] = "ingestion:no_unprocessed_posts"
            else:
                out["stage_failure"] = f"summarize:{idle}"
        elif raw_unprocessed > 0 and drafts_total == 0:
            out["stage_failure"] = "summarize:never_created_draft"
        else:
            ticks = conn.execute(
                """
                SELECT detail_json FROM pipeline_ticks
                ORDER BY id DESC LIMIT 3
                """
            ).fetchall()
            recent_dc = []
            for (det,) in ticks:
                try:
                    d = json.loads(det or "{}")
                    recent_dc.append(int(d.get("drafts_created") or 0))
                except Exception:
                    recent_dc.append(0)
            out["checks"]["recent_tick_drafts_created"] = recent_dc
            if recent_dc and all(x == 0 for x in recent_dc):
                out["stage_failure"] = "summarize:three_ticks_zero_drafts"
            else:
                out["stage_failure"] = "unknown:check_logs_for_openai_summarize_failed"

        circuit_state = (health.get("runtime") or {}).get("openai_circuit_state")
        out["checks"]["openai_circuit_state"] = circuit_state
        out["checks"]["upstream_state_computed"] = upstream_pipeline_state(
            ctx_ai_enabled=bool(health.get("ai_pipeline_enabled")),
            circuit_allows=circuit_state != "open",
        )
    finally:
        conn.close()

    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Verify upstream draft generation")
    p.add_argument("--watch-ticks", type=int, default=0, help="Wait for N tick samples (slow)")
    args = p.parse_args()
    report = verify(watch_ticks=args.watch_ticks)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("ok"):
        print("\nDRAFT GENERATION: OK")
        return 0
    print(f"\nDRAFT GENERATION FAILED: {report.get('stage_failure')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
