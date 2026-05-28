"""Publish decision audit helpers (structured logs only)."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def lookup_source_tick_id(conn: sqlite3.Connection, draft_id: int) -> str:
    row = conn.execute(
        """
        SELECT tick_id FROM pipeline_ticks
        WHERE json_extract(detail_json,'$.draft_id') = ?
        ORDER BY id DESC LIMIT 1
        """,
        (draft_id,),
    ).fetchone()
    return str(row[0]) if row else ""


def log_publish_audit(
    *,
    draft_id: int,
    publish_decision: str,
    publish_mode: str,
    publish_source_tick_id: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    fields: dict[str, Any] = {
        "draft_id": draft_id,
        "publish_decision": publish_decision,
        "publish_mode": publish_mode,
        "publish_source_tick_id": publish_source_tick_id or "",
    }
    if extra:
        fields.update(extra)
    log_event(logger, "publish.audit", **fields)


def resolve_publish_mode(settings: Any) -> str:
    try:
        from app.ops.runtime_control import load_runtime_control

        return load_runtime_control(settings.runtime_state_dir).value
    except Exception:
        return "unknown"
