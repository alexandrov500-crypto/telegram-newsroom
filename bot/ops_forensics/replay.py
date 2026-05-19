from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.storage.db import default_db_path, init_database
from bot.storage.editorial_repository import EditorialRepository


def replay_publish_forensics(
    publish_id: int | str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Read-only forensic reconstruction of a publish decision.
    Does NOT send to Telegram or mutate live state.
    """
    path = db_path or default_db_path()
    init_database(path)
    pid = int(publish_id)

    from bot.live_ops.publish_trace import PublishTraceStore
    from bot.ops_forensics.repository import ForensicsRepository

    editorial = EditorialRepository(path)
    item = editorial.get_by_id(pid)
    trace = PublishTraceStore(path).get(pid)
    repo = ForensicsRepository(path)

    timeline = repo.query_timeline(publish_id=pid, limit=500)
    audit = repo.query_audit(publish_id=pid, limit=200)
    correlation_id = None
    if trace:
        correlation_id = trace.get("correlation_id")
    if not correlation_id and timeline:
        correlation_id = timeline[0].get("correlation_id")
    if correlation_id:
        timeline = repo.query_timeline(correlation_id=correlation_id, limit=500)
        audit = repo.query_audit(correlation_id=correlation_id, limit=200)

    payload_preview: dict[str, Any] = {}
    if item is not None:
        payload_preview = {
            "title": item.title,
            "optimized_headline": item.optimized_headline,
            "hook_line": item.hook_line,
            "summary": (item.summary or "")[:500],
            "link": item.link,
            "source": item.source,
            "tags": item.tags,
            "cluster_id": item.cluster_id,
            "status": item.status,
        }

    guard_reconstruction = {
        "trace_guard_result": trace.get("guard_result") if trace else None,
        "trace_blockers": trace.get("blockers") if trace else None,
        "scores": {
            "confidence": trace.get("confidence_score") if trace else None,
            "trust": trace.get("trust_score") if trace else None,
            "safety": trace.get("safety_score") if trace else None,
        },
        "operator_override": trace.get("operator_override") if trace else None,
        "mode": trace.get("mode") if trace else None,
    }

    return {
        "replay_mode": "read_only_forensic",
        "publish_id": pid,
        "correlation_id": correlation_id,
        "source_input": payload_preview,
        "guard_decisions": guard_reconstruction,
        "publish_trace": trace,
        "timeline_events": timeline,
        "audit_log": audit,
        "telegram_payload_note": (
            "Reconstructed from pending_news fields; actual sent HTML not stored separately."
        ),
    }
