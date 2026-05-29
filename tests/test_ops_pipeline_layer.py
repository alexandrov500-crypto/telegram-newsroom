from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.editorial.scoring_engine import score_story
from app.reliability.idempotency import (
    build_publish_idempotency_key,
    is_idempotency_processed,
    mark_idempotency_processed,
)
from app.reliability.shutdown import reset_shutdown_for_tests
from ops.pipeline.checkpoint_store import load_checkpoint, save_checkpoint
from ops.pipeline.dedup_engine import DedupEngine
from ops.pipeline.ingestion_ledger import IngestionLedger
from ops.pipeline.source_circuit import SourceCircuitBreaker
from ops.pipeline.state_machine import NewsState, transition_allowed


@pytest.fixture(autouse=True)
def _reset_ops_state():
    reset_shutdown_for_tests()
    yield


def test_state_machine_transitions():
    assert transition_allowed(NewsState.NEW, NewsState.VALIDATED)
    assert not transition_allowed(NewsState.NEW, NewsState.PUBLISHED)
    assert not transition_allowed(NewsState.PUBLISHED, NewsState.APPROVED)


def test_ingestion_ledger_append_and_latest(tmp_path: Path):
    led = IngestionLedger(str(tmp_path / "runtime"))
    led.append(news_id="n1", from_state=None, to_state=NewsState.NEW, decision_reason="ingest")
    led.append(
        news_id="n1",
        from_state=NewsState.NEW,
        to_state=NewsState.VALIDATED,
        decision_reason="ok",
    )
    assert led.latest_state("n1") == NewsState.VALIDATED


def test_dedup_l1_and_register(tmp_path: Path):
    dedup = DedupEngine(str(tmp_path / "runtime"))
    v1 = dedup.check(source="@ch", message_id=1, text="Hello market news today")
    assert not v1.duplicate
    dedup.register(source="@ch", message_id=1, text="Hello market news today")
    v2 = dedup.check(source="@ch", message_id=1, text="Hello market news today")
    assert v2.duplicate
    assert v2.stage == "L1"


def test_source_circuit_opens_after_failures(tmp_path: Path):
    cb = SourceCircuitBreaker(str(tmp_path / "runtime"))
    src = "@testsource"
    for _ in range(6):
        cb.record_failure(src, reason="timeout")
    ok, reason = cb.allow_fetch(src)
    assert not ok
    assert reason == "circuit_open"


def test_idempotency_index(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    key = build_publish_idempotency_key(
        source_id="@ch",
        external_message_id=99,
        content_hash="abc123",
        draft_id=1,
    )
    assert not is_idempotency_processed(rd, key)
    mark_idempotency_processed(rd, key, draft_id=1, channel_message_id=42)
    assert is_idempotency_processed(rd, key)


def test_checkpoint_atomic_write(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    save_checkpoint(rd, {"last_tick_id": "tick-1", "last_stable_state": "tick_completed"})
    ck = load_checkpoint(rd)
    assert ck["last_tick_id"] == "tick-1"
    path = tmp_path / "runtime" / "checkpoints" / "latest.json"
    assert path.is_file()


def test_scoring_engine_lane_breaking():
    s = score_story(
        text="BREAKING: central bank raises rates amid war escalation",
        sources=["@cb_economics", "@tnews365"],
    )
    assert s.lane in {"breaking", "normal", "discard"}
    assert s.final_priority_score >= 40


def test_scoring_discard_meme():
    s = score_story(text="лол мем 😂", sources=["@decenter"])
    assert s.lane == "discard"
