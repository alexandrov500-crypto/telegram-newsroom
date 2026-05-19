from __future__ import annotations

import logging
from typing import Any

from bot.ops_forensics.correlation import (
    ensure_correlation_id,
    get_correlation_id,
    get_publish_id,
)
from bot.ops_forensics.repository import ForensicsRepository

logger = logging.getLogger(__name__)

_repo: ForensicsRepository | None = None


def _repo_instance() -> ForensicsRepository:
    global _repo
    if _repo is None:
        _repo = ForensicsRepository()
    return _repo


def record_timeline(
    event_type: str,
    *,
    severity: str = "info",
    details: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    publish_id: str | int | None = None,
) -> None:
    try:
        _repo_instance().append_timeline(
            event_type=event_type,
            severity=severity,
            details=details or {},
            correlation_id=correlation_id or get_correlation_id(),
            publish_id=publish_id or get_publish_id(),
        )
    except Exception:
        logger.exception("event=forensics_timeline_failed type=%s", event_type)


def record_audit(
    action: str,
    *,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
    correlation_id: str | None = None,
    publish_id: str | int | None = None,
) -> str | None:
    try:
        return _repo_instance().append_audit(
            action=action,
            payload=payload or {},
            actor=actor,
            correlation_id=correlation_id or get_correlation_id(),
            publish_id=publish_id or get_publish_id(),
        )
    except Exception:
        logger.exception("event=forensics_audit_failed action=%s", action)
        return None


def record_publish_lifecycle(
    phase: str,
    *,
    pending_news_id: int,
    details: dict[str, Any] | None = None,
    severity: str = "info",
) -> str:
    cid = ensure_correlation_id(prefix="pub")
    merged = {"pending_news_id": pending_news_id, "phase": phase, **(details or {})}
    event_type = f"publish_{phase}"
    record_timeline(
        event_type,
        severity=severity,
        details=merged,
        correlation_id=cid,
        publish_id=pending_news_id,
    )
    return cid
