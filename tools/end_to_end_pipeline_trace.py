#!/usr/bin/env python3
"""
Full end-to-end pipeline trace: raw → summarize → desk → draft → publish → Telegram.

Usage:
  python3 tools/end_to_end_pipeline_trace.py
  python3 tools/end_to_end_pipeline_trace.py --draft-id 4
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


def _stage(name: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"stage": name, "status": status, **extra}


def trace(*, draft_id: int | None = None) -> dict[str, Any]:
    import sqlite3

    from app.recovery.pipeline_overrides import (
        is_force_ai_pipeline_enabled,
        is_force_publish_bypass,
        is_minimal_pipeline_mode,
    )

    stages: list[dict[str, Any]] = []
    breakpoint = "none"

    # 1. Runtime / health
    try:
        import urllib.request

        port = int(os.getenv("HEALTH_HTTP_PORT", "8080") or 0)
        if port > 0:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                health = json.loads(resp.read().decode())
            stages.append(
                _stage(
                    "runtime_health",
                    "ok",
                    ai_pipeline_enabled=health.get("ai_pipeline_enabled"),
                    upstream_pipeline_state=health.get("upstream_pipeline_state"),
                    pipeline_reconcile=health.get("pipeline_reconcile"),
                    polling_active=(health.get("dependencies") or {})
                    .get("telegram_api", {})
                    .get("polling_active"),
                    publish_outcome=(health.get("pipeline") or {}).get("publish_outcome"),
                    summarize_idle=(health.get("pipeline") or {}).get("summarize_idle"),
                )
            )
            rec = health.get("pipeline_reconcile") or {}
            if rec.get("summarize_enabled") and health.get("ai_pipeline_enabled") is False:
                stages.append(
                    _stage(
                        "state_reconcile_mismatch",
                        "warn",
                        detail="health ai_pipeline_enabled false but reconcile says summarize_enabled",
                    )
                )
            if health.get("ai_pipeline_enabled") is False and not is_force_ai_pipeline_enabled():
                breakpoint = "upstream:ai_pipeline_disabled"
        else:
            stages.append(_stage("runtime_health", "skip", reason="no HEALTH_HTTP_PORT"))
    except Exception as exc:
        stages.append(_stage("runtime_health", "fail", error=repr(exc)))
        breakpoint = "runtime:health_unreachable"

    path = _db_path()
    if not path or not Path(path).is_file():
        stages.append(_stage("database", "fail", error="no sqlite"))
        return {"breakpoint": "database:missing", "stages": stages}

    conn = sqlite3.connect(path)
    try:
        # 2. Raw ingestion
        raw_total = conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
        raw_unprocessed = conn.execute(
            "SELECT COUNT(*) FROM raw_posts WHERE processed_at IS NULL"
        ).fetchone()[0]
        stages.append(
            _stage(
                "raw_ingestion",
                "ok" if raw_total else "empty",
                raw_total=raw_total,
                raw_unprocessed=raw_unprocessed,
            )
        )
        if raw_unprocessed == 0 and raw_total == 0 and breakpoint == "none":
            breakpoint = "ingestion:no_raw_posts"

        # 3–5. Recent tick detail (summarize / cluster / desk proxy)
        tick = conn.execute(
            """
            SELECT id, status, posts_collected, drafts_created, detail_json
            FROM pipeline_ticks ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if tick:
            tid, st, pc, dc, det = tick
            detail: dict[str, Any] = {}
            try:
                detail = json.loads(det or "{}")
            except Exception:
                pass
            summarize_status = "idle" if int(dc or 0) == 0 else "produced_draft"
            if detail.get("summarize_idle"):
                summarize_status = f"idle:{detail['summarize_idle']}"
            stages.append(
                _stage(
                    "summarize_cluster_desk",
                    summarize_status,
                    tick_id=tid,
                    tick_status=st,
                    posts_collected=pc,
                    drafts_created=dc,
                    summarize_idle=detail.get("summarize_idle"),
                    timings=detail.get("timings"),
                )
            )
            if int(dc or 0) == 0 and raw_unprocessed > 0 and breakpoint == "none":
                idle = str(detail.get("summarize_idle") or "")
                if idle.startswith("desk_reject"):
                    breakpoint = f"desk:{idle}"
                elif idle:
                    breakpoint = f"upstream:{idle}"
                else:
                    breakpoint = "upstream:summarize_no_draft"
        else:
            stages.append(_stage("summarize_cluster_desk", "fail", error="no pipeline_ticks"))

        # 6. Draft creation
        drafts_by_status = {
            str(a): b
            for a, b in conn.execute("SELECT status, COUNT(*) FROM drafts GROUP BY status").fetchall()
        }
        stages.append(_stage("draft_creation", "ok" if drafts_by_status else "empty", **drafts_by_status))

        target_id = draft_id
        if target_id is None:
            row = conn.execute(
                """
                SELECT id FROM drafts
                WHERE status IN ('pending','approved','scheduled','publishing','published','failed')
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            target_id = int(row[0]) if row else None

        if target_id is None:
            stages.append(_stage("publish_attempt", "skip", reason="no_draft"))
            if breakpoint == "none":
                breakpoint = "draft:none"
        else:
            row = conn.execute(
                "SELECT id, status, content, sources, draft_extras, channel_message_id FROM drafts WHERE id=?",
                (target_id,),
            ).fetchone()
            if not row:
                stages.append(_stage("publish_attempt", "fail", draft_id=target_id))
                breakpoint = f"draft:{target_id}_missing"
            else:
                did, status, content, sources, extras, msg_id = row
                stages.append(
                    _stage(
                        "draft_record",
                        status,
                        draft_id=did,
                        has_content=bool((content or "").strip()),
                        channel_message_id=msg_id,
                    )
                )

                from app.config import load_settings
                from app.editorial.final_publish_gate import evaluate_final_publish_gate

                settings = load_settings()
                gate_sched = evaluate_final_publish_gate(
                    content=content or "",
                    sources=sources or "[]",
                    draft_extras_json=extras,
                    settings=settings,
                    operator_approved=False,
                    draft_id=did,
                )
                gate_ops = evaluate_final_publish_gate(
                    content=content or "",
                    sources=sources or "[]",
                    draft_extras_json=extras,
                    settings=settings,
                    operator_approved=True,
                    draft_id=did,
                )
                stages.append(
                    _stage(
                        "publish_gate",
                        "allow" if gate_ops.allowed else "block",
                        scheduled=gate_sched.to_dict(),
                        operator_bypass=gate_ops.to_dict(),
                    )
                )

                if status == "published" and msg_id:
                    stages.append(
                        _stage("telegram_send", "ok", message_id=msg_id, draft_id=did)
                    )
                    breakpoint = "none" if breakpoint.startswith("upstream") else "none"
                elif status == "failed":
                    stages.append(_stage("telegram_send", "fail", draft_id=did, status=status))
                    if breakpoint == "none":
                        breakpoint = f"downstream:draft_{did}_failed"
                elif not gate_ops.allowed and not (
                    is_minimal_pipeline_mode() or is_force_publish_bypass()
                ):
                    stages.append(
                        _stage(
                            "publish_attempt",
                            "blocked",
                            reason=gate_sched.reason,
                        )
                    )
                    if breakpoint == "none":
                        breakpoint = f"downstream:final_gate:{gate_sched.reason}"
                else:
                    stages.append(
                        _stage(
                            "publish_attempt",
                            "pending",
                            hint="run recover_publish_draft.py or wait for scheduled publish",
                        )
                    )
                    if breakpoint == "none" and status == "pending":
                        breakpoint = "downstream:pending_not_published"
    finally:
        conn.close()

    stages.append(
        _stage(
            "recovery_flags",
            "info",
            FORCE_AI_PIPELINE_ENABLED=is_force_ai_pipeline_enabled(),
            MINIMAL_PIPELINE_MODE=is_minimal_pipeline_mode(),
            FORCE_PUBLISH_BYPASS=is_force_publish_bypass(),
        )
    )

    return {
        "breakpoint": breakpoint,
        "stages": stages,
        "recovery": {
            "enable_for_debug": [
                "FORCE_AI_PIPELINE_ENABLED=true",
                "MINIMAL_PIPELINE_MODE=true",
                "FORCE_PUBLISH_BYPASS=true",
            ],
            "disable_after_restore": [
                "unset all three flags and restart",
            ],
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="End-to-end pipeline trace")
    p.add_argument("--draft-id", type=int, default=None)
    args = p.parse_args()
    report = trace(draft_id=args.draft_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nPIPELINE BREAKPOINT: {report['breakpoint']}")
    return 0 if report["breakpoint"] in ("none",) else 1


if __name__ == "__main__":
    raise SystemExit(main())
