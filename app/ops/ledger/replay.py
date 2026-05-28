"""REPLAY_MODE — deterministic replay from event ledger (no Telegram reads)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def replay_mode_enabled() -> bool:
    return os.getenv("REPLAY_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


def replay_batch_limit() -> int:
    try:
        return max(1, int(os.getenv("REPLAY_BATCH_LIMIT", "50")))
    except ValueError:
        return 50


async def run_replay_collect_step(ctx: Any) -> int:
    """
    Replay INGESTED ledger events through the router (no Telethon).
    Returns number of events replayed this tick.
    """
    from app.observability import ledger_metrics as lm
    from app.ops.ledger.event_ledger import get_event_ledger
    from app.ops.ledger.writer import record_dropped
    from app.ops.priority_router import route_message_event
    from utils.structured_log import log_event

    ledger = get_event_ledger()
    if ledger is None:
        logger.warning("replay skipped: event ledger not initialized")
        return 0

    cursor = ledger.get_replay_cursor()
    events = ledger.fetch_ingested_for_replay(after_event_id=cursor, limit=replay_batch_limit())
    if not events:
        lm.set_replay_lag_sec(0.0)
        log_event(logger, "replay.idle", reason="no_pending_events")
        return 0

    t0 = time.time()
    replayed = 0
    last_id: str | None = cursor

    for ev in events:
        payload = dict(ev.get("payload") or {})
        item = {
            "news_id": payload.get("news_id"),
            "ingest_key": payload.get("ingest_key"),
            "source": ev.get("channel") or payload.get("source"),
            "channel_name": ev.get("channel"),
            "message_id": ev.get("message_id"),
            "text": payload.get("text") or payload.get("text_preview") or payload.get("body") or "",
            "runtime_dir": payload.get("runtime_dir") or getattr(ctx.settings, "runtime_state_dir", None),
            "ingested_at_unix": ev.get("timestamp_unix"),
            "replay": True,
            "ledger_event_id": ev.get("event_id"),
        }
        try:
            decision = route_message_event(item)
            if decision is None or decision.dropped:
                record_dropped(item, reason="replay_route_skipped")
            replayed += 1
            last_id = str(ev.get("event_id"))
        except Exception as exc:
            logger.warning("replay event failed id=%s: %s", ev.get("event_id"), exc)
            record_dropped(item, reason=f"replay_error:{exc!s}"[:120])

    if last_id and last_id != cursor:
        ledger.set_replay_cursor(last_id)

    lag = time.time() - float(events[-1].get("timestamp_unix") or t0)
    lm.set_replay_lag_sec(lag)
    log_event(
        logger,
        "replay.batch",
        replayed=replayed,
        cursor=last_id,
        lag_sec=round(lag, 2),
    )
    logger.info("REPLAY_MODE batch replayed=%s cursor=%s lag_sec=%.1f", replayed, last_id, lag)
    return replayed
