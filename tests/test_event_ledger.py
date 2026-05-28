from __future__ import annotations

import pytest

from app.ingestion.idempotency import message_fingerprint
from app.ops.ledger.event_ledger import (
    EventType,
    LedgerEvent,
    init_event_ledger,
    is_duplicate_event,
    reset_event_ledger_for_tests,
)
from app.ops.ledger.writer import record_dropped, record_ingested, record_published, record_routed


@pytest.fixture(autouse=True)
def _ledger(tmp_path):
    reset_event_ledger_for_tests()
    init_event_ledger(str(tmp_path / "rt"))
    yield
    reset_event_ledger_for_tests()


def test_fingerprint_dedup_and_ingested():
    item = {
        "channel_name": "@news",
        "message_id": 42,
        "text": "Breaking story",
        "news_id": "n1",
        "ingest_key": "k1",
    }
    fp = message_fingerprint("@news", 42)
    assert not is_duplicate_event(fp)
    eid = record_ingested(item)
    assert eid
    assert is_duplicate_event(fp)
    assert record_ingested(item) is None


def test_dropped_and_routed_events(tmp_path):
    item = {
        "channel_name": "@cb",
        "message_id": 7,
        "news_id": "x",
        "source": "@cb",
    }
    record_dropped(item, reason="test_filter")
    record_routed(item, lane="fast", reason="breaking_flag")
    record_published(item, channel_message_id=999, lane="breaking")

    from app.ops.ledger.event_ledger import get_event_ledger

    ledger = get_event_ledger()
    assert ledger is not None
    counts = ledger.count_by_type()
    assert counts.get("DROPPED", 0) >= 1
    assert counts.get("ROUTED", 0) >= 1
    assert counts.get("PUBLISHED", 0) >= 1


def test_replay_fetch_order(tmp_path):
    from app.ops.ledger.event_ledger import get_event_ledger

    ledger = get_event_ledger()
    for mid in (1, 2, 3):
        record_ingested(
            {
                "channel_name": "@x",
                "message_id": mid,
                "text": f"story {mid}",
                "news_id": f"n{mid}",
            }
        )
    events = ledger.fetch_ingested_for_replay(limit=10)
    assert len(events) == 3
    assert events[0]["message_id"] == 1
    assert events[2]["message_id"] == 3


def test_duplicate_ingest_claim_raises():
    item = {"channel_name": "@a", "message_id": 99, "text": "t", "news_id": "a"}
    assert record_ingested(item)
    ev = LedgerEvent(
        event_type=EventType.INGESTED,
        channel="@a",
        message_id=99,
        fingerprint=message_fingerprint("@a", 99),
        payload={},
    )
    from app.ops.ledger.event_ledger import get_event_ledger

    ledger = get_event_ledger()
    with pytest.raises(ValueError, match="fingerprint_already_claimed"):
        ledger.append(ev, claim_fingerprint=True)
