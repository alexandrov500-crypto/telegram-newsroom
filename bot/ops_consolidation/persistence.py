from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bot.storage.db import init_database


PERSISTENCE_OWNERS: list[dict[str, Any]] = [
    {
        "tables": ["live_publish_trace", "live_channel_post_ratings"],
        "owner": "live_ops",
        "retention": "ops_lifecycle OPS_RETAIN_PUBLISH_TRACE_DAYS",
    },
    {
        "tables": ["ops_trust_calibration_events", "ops_trust_subsystem_daily", "ops_trust_calibration_daily"],
        "owner": "trust_calibration",
        "retention": "90d events / daily rollups",
    },
    {
        "tables": ["ops_evidence_reviews"],
        "owner": "ops_evidence",
        "retention": "indefinite weekly archives",
    },
    {
        "tables": ["ops_resilience_state", "ops_resilience_events", "ops_resilience_daily"],
        "owner": "ops_resilience",
        "retention": "state live; events 30d; daily 90d",
    },
    {
        "tables": ["ops_attention_log", "ops_attention_daily"],
        "owner": "operator_ux",
        "retention": "log 14d; daily 30d",
    },
    {
        "tables": ["editorial_quality_scores", "editorial_quality_daily"],
        "owner": "editorial_quality",
        "retention": "scores 30d; daily 90d",
    },
    {
        "tables": ["editorial_priority_scores", "editorial_priority_daily"],
        "owner": "editorial_priority",
        "retention": "scores 30d; daily 90d",
    },
    {
        "tables": ["editorial_storylines", "editorial_story_events"],
        "owner": "editorial_memory",
        "retention": "storyline lifecycle + archive",
    },
    {
        "tables": ["live_incident_timeline", "live_operational_audit"],
        "owner": "ops_forensics",
        "retention": "forensic; lifecycle prune",
    },
    {
        "tables": ["ops_lifecycle_runs", "ops_lifecycle_daily"],
        "owner": "ops_lifecycle",
        "retention": "runs 30d; daily 180d",
    },
    {
        "tables": ["var/ops/pulses", "var/ops/daily"],
        "owner": "ops_observation",
        "retention": "pulse compaction via lifecycle",
    },
]


def persistence_audit(db_path: Path) -> dict[str, Any]:
    init_database(db_path)
    overlaps: list[str] = []
    issues: list[str] = []

    table_sets = [set(o["tables"]) for o in PERSISTENCE_OWNERS]
    for i, a in enumerate(table_sets):
        for b in table_sets[i + 1 :]:
            inter = a & b
            if inter:
                overlaps.append(f"duplicate ownership claim: {inter}")

    ops_tables: list[str] = []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ops_%' ORDER BY name",
        ).fetchall()
        ops_tables = [r[0] for r in rows]

    claimed = {t for o in PERSISTENCE_OWNERS for t in o["tables"] if not t.startswith("var/")}
    unclaimed_ops = [t for t in ops_tables if t not in claimed]

    if unclaimed_ops:
        issues.append(f"ops_* tables without documented owner: {unclaimed_ops[:12]}")

    return {
        "owners": PERSISTENCE_OWNERS,
        "ops_table_count": len(ops_tables),
        "documented_table_count": len(claimed),
        "unclaimed_ops_tables": unclaimed_ops,
        "ownership_overlaps": overlaps,
        "issues": issues,
    }
