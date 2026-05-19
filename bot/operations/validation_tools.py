from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bot.operations.feed_validation import FeedValidationLayer
from bot.operations.repository import OperationsRepository
from bot.staging.feeds_config import catalog_for_validation


def replay_inspection_report(db_path: Path, *, limit: int = 20) -> str:
    lines = ["Replay inspection (recent sourced events):"]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, created_at, trace_id
                FROM sourced_event_log ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            return f"Replay unavailable: {exc}"
    if not rows:
        lines.append("  (no events)")
        return "\n".join(lines)
    for r in rows:
        tid = r["trace_id"] if "trace_id" in r.keys() else ""
        lines.append(f"  {r['created_at'][-19:]} {r['event_type']} id={r['event_id']} trace={tid}")
    return "\n".join(lines)


def contradiction_inspection_report(db_path: Path, *, limit: int = 15) -> str:
    repo = OperationsRepository(db_path)
    lines = ["Open contradictions:"]
    with repo._connect() as conn:
        try:
            rows = conn.execute(
                """
                SELECT contradiction_id, severity, subject_type, explanation
                FROM epistemic_contradictions WHERE status = 'open'
                ORDER BY severity DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except Exception as exc:
            return f"Contradictions unavailable: {exc}"
    if not rows:
        lines.append("  (none)")
        return "\n".join(lines)
    for r in rows:
        lines.append(
            f"  {r['contradiction_id']} [{r['subject_type']}] sev={r['severity']:.2f} "
            f"{str(r['explanation'])[:80]}"
        )
    return "\n".join(lines)


def cognition_lineage_dump(db_path: Path, *, limit: int = 10) -> str:
    lines = ["Cognition lineage (mesh events):"]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT event_id, event_type, node_id, created_at
                FROM mesh_cognitive_events ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            return f"Lineage unavailable: {exc}"
    for r in rows:
        lines.append(f"  {r['created_at'][-19:]} {r['node_id']} {r['event_type']}")
    return "\n".join(lines) if len(lines) > 1 else "\n".join(lines + ["  (none)"])


def event_amplification_report(db_path: Path) -> str:
    counts = OperationsRepository(db_path).table_row_counts()
    sourced = counts.get("sourced_event_log", 0)
    mesh = counts.get("mesh_cognitive_events", 0)
    pending = counts.get("pending_news", 0)
    ratio = mesh / max(sourced, 1)
    lines = [
        "Event amplification:",
        f"  sourced_event_log: {sourced}",
        f"  mesh_cognitive_events: {mesh}",
        f"  pending_news: {pending}",
        f"  mesh/sourced ratio: {ratio:.2f}",
    ]
    if ratio > 5.0:
        lines.append("  WARN: high amplification — review federation gossip")
    return "\n".join(lines)


def feed_reliability_report(db_path: Path, *, catalog_path: str | None = None) -> str:
    layer = FeedValidationLayer(OperationsRepository(db_path))
    cat = catalog_for_validation(catalog_path) if catalog_path else None
    results = layer.validate_catalog(cat)
    lines = ["Feed reliability:"]
    for r in sorted(results, key=lambda x: x.reliability):
        status = "OK" if r.reliability >= 0.4 else "WARN"
        lines.append(
            f"  [{status}] {r.source_name}: rel={r.reliability:.2f} "
            f"items={r.items_fetched} dup={r.duplicates} mal={r.malformed}"
        )
    return "\n".join(lines)


def burnin_summary_export(db_path: Path) -> str:
    repo = OperationsRepository(db_path)
    active = repo.active_burnin()
    if not active:
        return "No active burn-in run."
    samples = repo.burnin_samples(active["run_id"], limit=5)
    lines = [
        f"Burn-in {active['run_id']} profile={active.get('profile')}",
        f"  samples (latest): {len(samples)}",
    ]
    if samples:
        m = json.loads(samples[-1]["metrics_json"])
        lines.append(f"  last health={m.get('health_score')} backlog={m.get('queue_backlog')}")
    return "\n".join(lines)
