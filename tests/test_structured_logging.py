from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from utils.structured_log import log_event


def test_log_event_plain_message(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    log_event(log, "simple.event")
    assert any("simple.event" in r.message for r in caplog.records)


def test_log_event_json_payload_serializable(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    log_event(log, "payload.event", count=3, ok=True, ratio=0.5)
    rec = [r for r in caplog.records if "payload.event" in r.message][0]
    assert "|" in rec.message
    tail = rec.message.split("|", 1)[1].strip()
    data = json.loads(tail)
    assert data["count"] == 3 and data["ok"] is True and data["ratio"] == 0.5
    assert "event_id" in data


def test_log_event_truncates_long_strings(monkeypatch, caplog):
    monkeypatch.setenv("LOG_MAX_FIELD_LEN", "80")
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    long_text = "x" * 500
    log_event(log, "trunc.event", sample=long_text)
    rec = [r for r in caplog.records if "trunc.event" in r.message][0]
    tail = rec.message.split("|", 1)[1].strip()
    data = json.loads(tail)
    assert "…" in data["sample"] or len(data["sample"]) < len(long_text)
    assert len(data["sample"]) <= 200


def test_log_event_bytes_field(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    log_event(log, "bytes.event", blob=b"\xff\x00")
    rec = [r for r in caplog.records if "bytes.event" in r.message][0]
    assert "blob" in rec.message


def test_log_event_non_json_serializable_uses_default_str(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    log_event(log, "dt.event", when=datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    rec = [r for r in caplog.records if "dt.event" in r.message][0]
    assert "when" in rec.message


def test_log_event_typeerror_fallback(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")

    def bad_dumps(*a, **k):
        raise TypeError("boom")

    monkeypatch.setattr("utils.structured_log.json.dumps", bad_dumps)
    log_event(log, "fallback.event", x=1)
    assert any("fallback.event" in r.message for r in caplog.records)


def test_log_event_complex_nested_dict(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_structured")
    log_event(log, "nested.event", meta={"a": 1, "b": {"c": 2}})
    rec = [r for r in caplog.records if "nested.event" in r.message][0]
    tail = rec.message.split("|", 1)[1].strip()
    assert json.loads(tail)["meta"]["b"]["c"] == 2


def test_log_event_no_crash_on_logger(mock_log):
    log_event(mock_log, "ok", field=object())
    mock_log.info.assert_called_once()


@pytest.fixture
def mock_log():
    return MagicMock(spec=logging.Logger)
