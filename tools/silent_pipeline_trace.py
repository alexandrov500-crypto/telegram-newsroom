#!/usr/bin/env python3
"""
Locate pipeline breakpoint for silent / no-output newsroom state.

Usage:
  python3 tools/silent_pipeline_trace.py
  python3 tools/silent_pipeline_trace.py --draft-id 4
"""

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

from dotenv import load_dotenv

load_dotenv()


def _db_path() -> str | None:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    return sqlite_path_from_url(raw)


def _section(title: str, body: dict[str, Any]) -> dict[str, Any]:
    return {"title": title, **body}


def trace(*, draft_id: int | None = None) -> dict[str, Any]:
    import sqlite3

    out: dict[str, Any] = {"breakpoint": "unknown", "sections": []}

    # Runtime / health
    try:
        import urllib.request

        port = int(os.getenv("HEALTH_HTTP_PORT", "8080") or 0)
        if port > 0:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=4) as resp:
                health = json.loads(resp.read().decode())
            out["sections"].append(
                _section(
                    "runtime_health",
                    {
                        "status": health.get("status"),
                        "ai_pipeline_enabled": health.get("ai_pipeline_enabled"),
                        "startup_complete": health.get("startup_complete"),
                        "polling_active": (health.get("dependencies") or {})
                        .get("telegram_api", {})
                        .get("polling_active"),
                        "pipeline": health.get("pipeline"),
                        "summarize_idle": (health.get("pipeline") or {}).get("summarize_idle"),
                        "publish_outcome": (health.get("pipeline") or {}).get("publish_outcome"),
                    },
                )
            )
            if health.get("ai_pipeline_enabled") is False:
                out["breakpoint"] = "upstream:ai_pipeline_disabled"
    except Exception as exc:
        out["sections"].append(_section("runtime_health", {"error": repr(exc)}))

    path = _db_path()
    if not path or not Path(path).is_file():
        out["sections"].append(_section("database", {"error": "no sqlite db"}))
        return out

    conn = sqlite3.connect(path)
    try:
        drafts = conn.execute(
            "SELECT status, COUNT(*) FROM drafts GROUP BY status"
        ).fetchall()
        unprocessed = conn.execute(
            "SELECT COUNT(*) FROM raw_posts WHERE processed_at IS NULL"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status='pending'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE status='failed'"
        ).fetchone()[0]
        ticks = conn.execute(
            """
            SELECT status, posts_collected, drafts_created, detail_json
            FROM pipeline_ticks ORDER BY id DESC LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()

    out["sections"].append(
        _section(
            "database",
            {
                "drafts_by_status": {str(a): b for a, b in drafts},
                "raw_unprocessed": unprocessed,
                "drafts_pending": pending,
                "drafts_failed": failed,
            },
        )
    )

    tick_rows = []
    for st, pc, dc, det in ticks:
        detail = {}
        try:
            detail = json.loads(det or "{}")
        except Exception:
            pass
        tick_rows.append(
            {
                "status": st,
                "posts_collected": pc,
                "drafts_created": dc,
                "summarize_idle": detail.get("summarize_idle"),
                "publish_outcome": detail.get("publish_outcome"),
            }
        )
    out["sections"].append(_section("pipeline_ticks", {"recent": tick_rows}))

    if unprocessed > 0 and pending == 0 and failed == 0:
        out["breakpoint"] = "upstream:desk_or_cluster_no_drafts"
    elif unprocessed > 100 and all(t.get("drafts_created", 0) == 0 for t in tick_rows[:3]):
        if out["breakpoint"] == "unknown":
            out["breakpoint"] = "upstream:summarize_not_creating_drafts"
    elif pending > 0:
        out["breakpoint"] = "downstream:pending_awaiting_approval_or_schedule"
    elif failed > 0 and pending == 0:
        out["breakpoint"] = "downstream:failed_drafts_need_recovery"

    if draft_id is not None:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT id, status, content, sources, draft_extras FROM drafts WHERE id=?",
            (draft_id,),
        ).fetchone()
        conn.close()
        if row:
            from app.config import load_settings
            from app.editorial.final_publish_gate import evaluate_final_publish_gate

            settings = load_settings()
            gate_user = evaluate_final_publish_gate(
                content=row[2] or "",
                sources=row[3] or "[]",
                draft_extras_json=row[4],
                settings=settings,
                operator_approved=False,
                draft_id=int(row[0]),
            )
            gate_admin = evaluate_final_publish_gate(
                content=row[2] or "",
                sources=row[3] or "[]",
                draft_extras_json=row[4],
                settings=settings,
                operator_approved=True,
                draft_id=int(row[0]),
            )
            out["sections"].append(
                _section(
                    f"draft_{draft_id}",
                    {
                        "status": row[1],
                        "gate_operator_false": gate_user.to_dict(),
                        "gate_operator_true": gate_admin.to_dict(),
                    },
                )
            )
            if row[1] == "failed":
                out["breakpoint"] = f"downstream:draft_{draft_id}_failed_retry"
            elif row[1] == "pending" and not gate_admin.allowed:
                out["breakpoint"] = f"downstream:final_publish_gate:{gate_user.reason}"

    out["recommendations"] = _recommendations(out["breakpoint"])
    return out


def _recommendations(bp: str) -> list[str]:
    rec: list[str] = []
    if "ai_pipeline_disabled" in bp:
        rec.append("Reset OpenAI circuit or fix API; verify /health ai_pipeline_enabled=true")
    if "pending" in bp:
        rec.append("Admin: /approve <id> then publish (uses bypass_cadence after fix)")
    if "failed" in bp:
        rec.append("Run: python3 tools/recover_publish_draft.py <id> --bypass-cadence")
    if "summarize_not_creating" in bp:
        rec.append("Check logs for desk_reject / ai_budget / load_shedding; run with LOG_LEVEL=INFO")
    if "final_publish_gate" in bp:
        rec.append("Use /approve with bypass OR set MINIMAL_NEWSROOM_MODE=true for debug")
    if not rec:
        rec.append("Run: python3 tools/final_staging_validator.py")
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description="Silent pipeline breakpoint tracer")
    p.add_argument("--draft-id", type=int, default=None)
    args = p.parse_args()
    report = trace(draft_id=args.draft_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nPIPELINE BREAKPOINT: {report['breakpoint']}")
    print("Recommendations:")
    for r in report.get("recommendations") or []:
        print(f"  - {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
