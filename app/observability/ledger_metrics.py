"""Metrics and structured logs for the event ledger."""

from __future__ import annotations

import logging
from typing import Any

from app.ops.ledger.event_ledger import EventType
from utils.metrics import inc, set_gauge

logger = logging.getLogger(__name__)

_replay_lag_sec: float = 0.0


def record_ledger_append(event_type: EventType | str, fingerprint: str) -> None:
    et = event_type.value if hasattr(event_type, "value") else str(event_type).upper()
    inc("ledger_events_total")
    inc(f"ledger_{et.lower()}_total")


def record_ledger_drop(reason: str) -> None:
    inc("ledger_dropped_duplicates_total")
    inc(f"ledger_drop_{reason[:40].lower().replace(' ', '_')}_total")


def set_replay_lag_sec(sec: float) -> None:
    global _replay_lag_sec
    _replay_lag_sec = max(0.0, sec)
    set_gauge("ledger_replay_lag_sec", sec)


def log_ledger_event(
    *,
    event_type: str,
    fingerprint: str,
    channel: str,
    message_id: int,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        from app.runtime_lifecycle import runtime_id

        rid = runtime_id()
    except Exception:
        rid = "unknown"
    msg = (
        f"[LEDGER] event={event_type} fingerprint={fingerprint[:16]} "
        f"runtime_id={rid} channel={channel} message_id={message_id}"
    )
    if extra:
        msg += f" {extra}"
    logger.info(msg)


def ledger_snapshot() -> dict[str, Any]:
    from app.ops.ledger.event_ledger import get_event_ledger

    ledger = get_event_ledger()
    if ledger is None:
        return {"initialized": False}
    by_type = ledger.count_by_type()
    return {
        "initialized": True,
        "total_events": ledger.total_events(),
        "ingested_events": by_type.get("INGESTED", 0),
        "routed_events": by_type.get("ROUTED", 0),
        "dropped_events": by_type.get("DROPPED", 0),
        "published_events": by_type.get("PUBLISHED", 0),
        "dropped_duplicates": by_type.get("DROPPED", 0),
        "replay_lag_sec": _replay_lag_sec,
    }

