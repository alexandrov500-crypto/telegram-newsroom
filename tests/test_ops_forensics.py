from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.ops_forensics.correlation import (
    bind_publish_context,
    ensure_correlation_id,
    get_correlation_id,
    new_correlation_id,
)
from bot.ops_forensics.repository import ForensicsRepository


def test_correlation_context() -> None:
    cid = bind_publish_context(pending_news_id=42)
    assert cid.startswith("pub_")
    assert get_correlation_id() == cid


def test_timeline_append_only(tmp_path: Path) -> None:
    db = tmp_path / "forensics.db"
    repo = ForensicsRepository(db)
    repo.append_timeline(
        event_type="freeze_publishing",
        severity="warning",
        details={"reason": "test"},
        correlation_id="pub_test123",
        publish_id=7,
    )
    events = repo.query_timeline(publish_id=7)
    assert len(events) == 1
    assert events[0]["event_type"] == "freeze_publishing"


def test_audit_immutable_id(tmp_path: Path) -> None:
    db = tmp_path / "forensics.db"
    repo = ForensicsRepository(db)
    aid = repo.append_audit(action="mark_good_post", payload={"good": True}, publish_id=3)
    assert aid.startswith("aud_")
    entries = repo.query_audit(publish_id=3)
    assert entries[0]["action"] == "mark_good_post"


def test_baseline_lock(tmp_path: Path) -> None:
    db = tmp_path / "forensics.db"
    repo = ForensicsRepository(db)
    repo.lock_baseline({"event_loop_lag_max": 0.02}, notes="test")
    b = repo.get_baseline()
    assert b is not None
    assert b["event_loop_lag_max"] == 0.02
