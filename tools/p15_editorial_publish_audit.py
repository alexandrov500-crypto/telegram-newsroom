#!/usr/bin/env python3
"""P1.5 editorial & publish throughput audit (run inside container or against newsroom.db)."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/newsroom.db")
P10_DEPLOY = "2026-05-30 14:23:00"


def main() -> None:
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row

    def q(sql: str, *a: object) -> int:
        return int(c.execute(sql, a).fetchone()[0])

    def qa(sql: str, *a: object) -> list[sqlite3.Row]:
        return c.execute(sql, a).fetchall()

    print("=== 1. PIPELINE FUNNEL (24h) ===")
    raw_24 = q(
        "SELECT COUNT(*) FROM raw_posts WHERE collected_at >= datetime('now', '-24 hours')"
    )
    drafts_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours')"
    )
    rejected_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours') AND status='rejected'"
    )
    approved_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours') AND status='approved'"
    )
    published_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE status='published' AND created_at >= datetime('now', '-24 hours')"
    )
    failed_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours') AND status='failed'"
    )
    pending_24 = q(
        "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours') AND status='pending'"
    )
    queued_24 = q(
        """
        SELECT COUNT(*) FROM drafts
        WHERE scheduled_publish_at IS NOT NULL
          AND created_at >= datetime('now', '-24 hours')
        """
    )
    approved_backlog = q("SELECT COUNT(*) FROM drafts WHERE status='approved'")
    pending_backlog = q("SELECT COUNT(*) FROM drafts WHERE status='pending'")
    oldest_approved = c.execute(
        "SELECT id, created_at, scheduled_publish_at FROM drafts WHERE status='approved' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()

    def pct(n: int, d: int) -> str:
        return f"{100.0 * n / d:.1f}%" if d else "—"

    print(f"raw_posts={raw_24} drafts={drafts_24} rejected={rejected_24} approved={approved_24} published={published_24}")
    print(f"failed={failed_24} pending={pending_24} queued_scheduled={queued_24}")
    print(f"backlog approved={approved_backlog} pending={pending_backlog} oldest_approved={oldest_approved}")

    print("\n=== 2. REJECTION REASONS (last 100) ===")
    rows = qa(
        "SELECT id, created_at, draft_extras, sources FROM drafts WHERE status='rejected' ORDER BY id DESC LIMIT 100"
    )
    reasons: Counter[str] = Counter()
    risk_vals: list[float] = []
    for r in rows:
        ex = json.loads(r["draft_extras"] or "{}")
        ai = ex.get("ai_editorial_review") or {}
        reason = "unknown"
        if isinstance(ai, dict) and ai.get("reason"):
            reason = str(ai["reason"])
        elif ex.get("reject_reason"):
            reason = str(ex["reject_reason"])
        elif ex.get("desk_reason"):
            reason = str(ex["desk_reason"])
        elif isinstance(ex.get("edit_history"), list) and ex["edit_history"]:
            last = ex["edit_history"][-1]
            if isinstance(last, dict) and last.get("reason"):
                reason = str(last["reason"])
        reasons[reason] += 1
        pr = ex.get("publication_risk")
        if isinstance(pr, dict) and pr.get("score") is not None:
            try:
                risk_vals.append(float(pr["score"]))
            except (TypeError, ValueError):
                pass
        elif isinstance(ai, dict) and "publication_risk" in str(ai.get("reason", "")):
            reasons["publication_risk_gate"] += 0  # tagged via reason string

    for reason, count in reasons.most_common(20):
        print(f"  {count:3d} ({pct(count, len(rows)):>6s})  {reason[:80]}")

    print("\n=== 3. APPROVAL → PUBLISH LATENCY ===")
    pub_rows = qa(
        """
        SELECT id, created_at, scheduled_publish_at, moderated_at, draft_extras
        FROM drafts
        WHERE status='published' AND created_at >= datetime('now', '-7 days')
        ORDER BY id DESC
        """
    )
    latencies: list[float] = []
    for r in pub_rows:
        created = r["created_at"]
        sched = r["scheduled_publish_at"]
        # proxy: scheduled_publish_at as publish time when set
        anchor = sched or created
        if created and anchor:
            try:
                t0 = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(str(anchor).replace("Z", "+00:00"))
                latencies.append(abs((t1 - t0).total_seconds()))
            except ValueError:
                pass
    latencies.sort()

    def percentile(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        i = int(len(vals) * p / 100)
        return vals[min(i, len(vals) - 1)]

    print(f"published_sample={len(pub_rows)} latency_samples={len(latencies)}")
    if latencies:
        print(f"  p50={percentile(latencies, 50):.1f}s p95={percentile(latencies, 95):.1f}s max={max(latencies):.1f}s")

    print("\n=== 4. THROUGHPUT BEFORE/AFTER P1.0 ===")
    for label, raw_sql, draft_sql, pub_sql in [
        (
            "before_P10_24h_window",
            "SELECT COUNT(*) FROM raw_posts WHERE collected_at >= datetime('now','-24 hours') AND collected_at < ?",
            "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now','-24 hours') AND created_at < ?",
            "SELECT COUNT(*) FROM drafts WHERE status='published' AND created_at >= datetime('now','-24 hours') AND created_at < ?",
        ),
        (
            "after_P10",
            "SELECT COUNT(*) FROM raw_posts WHERE collected_at >= ?",
            "SELECT COUNT(*) FROM drafts WHERE created_at >= ?",
            "SELECT COUNT(*) FROM drafts WHERE status='published' AND created_at >= ?",
        ),
    ]:
        if label.startswith("before"):
            raw_n = q(raw_sql, P10_DEPLOY)
            dr_n = q(draft_sql, P10_DEPLOY)
            pub_n = q(pub_sql, P10_DEPLOY)
        else:
            raw_n = q(raw_sql, P10_DEPLOY)
            dr_n = q(draft_sql, P10_DEPLOY)
            pub_n = q(pub_sql, P10_DEPLOY)
        hours = 24.0 if label.startswith("before") else max(
            0.5,
            (
                datetime.utcnow()
                - datetime.fromisoformat(P10_DEPLOY.replace(" ", "T"))
            ).total_seconds()
            / 3600,
        )
        print(
            f"{label}: raw={raw_n} ({raw_n/hours:.2f}/h) drafts={dr_n} ({dr_n/hours:.2f}/h) "
            f"published={pub_n} ({pub_n/hours:.2f}/h) window_hours={hours:.1f}"
        )

    print("\n=== 5. RAW UNPROCESSED ===")
    print("unprocessed_raw", q("SELECT COUNT(*) FROM raw_posts WHERE processed_at IS NULL"))


if __name__ == "__main__":
    main()
