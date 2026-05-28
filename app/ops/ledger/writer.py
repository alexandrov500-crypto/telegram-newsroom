"""Crash-safe ledger writer — single entry point for pipeline events."""

from __future__ import annotations

import logging
from typing import Any

from app.observability import ledger_metrics as lm
from app.ops.ledger.event_ledger import (
    EventLedger,
    EventType,
    LedgerEvent,
    event_fingerprint,
    get_event_ledger,
)

logger = logging.getLogger(__name__)


def _ledger() -> EventLedger | None:
    return get_event_ledger()


def _channel_mid(item: dict[str, Any]) -> tuple[str, int]:
    ch = str(item.get("channel_name") or item.get("source") or "")
    mid = int(item.get("message_id") or 0)
    return ch, mid


def append_event(event: LedgerEvent, *, claim_fingerprint: bool = False) -> str | None:
    """Append to ledger; returns event_id or None if ledger unavailable."""
    ledger = _ledger()
    if ledger is None:
        logger.warning("ledger append skipped: not initialized")
        return None
    try:
        eid = ledger.append(event, claim_fingerprint=claim_fingerprint)
        lm.record_ledger_append(event.event_type, event.fingerprint)
        lm.log_ledger_event(
            event_type=(
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            ),
            fingerprint=event.fingerprint,
            channel=event.channel,
            message_id=event.message_id,
            extra={"event_id": eid},
        )
        return eid
    except ValueError as exc:
        if "fingerprint_already_claimed" in str(exc):
            lm.record_ledger_drop("fingerprint_race")
            return None
        raise


def flush_event(event: LedgerEvent, **kwargs: Any) -> str | None:
    """Alias for append (SQLite commits per event)."""
    return append_event(event, **kwargs)


def record_ingested(item: dict[str, Any], *, extra: dict[str, Any] | None = None) -> str | None:
    ch, mid = _channel_mid(item)
    fp = event_fingerprint(ch, mid)
    text = str(item.get("text") or "")
    payload = {
        "news_id": item.get("news_id"),
        "ingest_key": item.get("ingest_key"),
        "text": text,
        "text_preview": text[:500],
        "runtime_dir": item.get("runtime_dir"),
        **(extra or {}),
    }
    ev = LedgerEvent(
        event_type=EventType.INGESTED,
        channel=ch,
        message_id=mid,
        fingerprint=fp,
        payload=payload,
    )
    return append_event(ev, claim_fingerprint=True)


def record_routed(item: dict[str, Any], *, lane: str, reason: str, **extra: Any) -> str | None:
    ch, mid = _channel_mid(item)
    ev = LedgerEvent(
        event_type=EventType.ROUTED,
        channel=ch,
        message_id=mid,
        fingerprint=event_fingerprint(ch, mid),
        payload={"lane": lane, "reason": reason, "news_id": item.get("news_id"), **extra},
    )
    return append_event(ev)


def record_dropped(
    item: dict[str, Any] | None,
    *,
    channel: str = "",
    message_id: int = 0,
    reason: str,
    fingerprint: str | None = None,
    **extra: Any,
) -> str | None:
    if item is not None:
        ch, mid = _channel_mid(item)
    else:
        ch, mid = channel, message_id
    fp = fingerprint or event_fingerprint(ch, mid)
    ev = LedgerEvent(
        event_type=EventType.DROPPED,
        channel=ch,
        message_id=mid,
        fingerprint=fp,
        payload={"reason": reason[:300], **extra},
    )
    out = append_event(ev)
    lm.record_ledger_drop(reason)
    return out


def record_published(
    item: dict[str, Any],
    *,
    channel_message_id: int | None = None,
    lane: str = "breaking",
    **extra: Any,
) -> str | None:
    ch, mid = _channel_mid(item)
    ev = LedgerEvent(
        event_type=EventType.PUBLISHED,
        channel=ch,
        message_id=mid,
        fingerprint=event_fingerprint(ch, mid),
        payload={
            "channel_message_id": channel_message_id,
            "lane": lane,
            "news_id": item.get("news_id"),
            **extra,
        },
    )
    return append_event(ev)
