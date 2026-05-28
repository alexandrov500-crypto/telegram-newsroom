from __future__ import annotations

import json
import logging

import pytest

from utils.operational_context import begin_pipeline_tick, reset_correlation_id, reset_tick_id, set_correlation_id
from utils.structured_log import log_event


def test_log_event_includes_deterministic_event_id(monkeypatch, caplog):
    monkeypatch.setenv("NEWSROOM_LOG_DETERMINISTIC_IDS", "1")
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_oplog")
    log_event(log, "op.sample", phase="alpha", ok=True)
    rec = [r for r in caplog.records if "op.sample" in r.message][0]
    msg = rec.message
    data = json.loads(msg[msg.index("{") :])
    assert data["event_id"] == "evt-000001"
    assert data["phase"] == "alpha"


def test_correlation_and_tick_context_merged(monkeypatch, caplog):
    monkeypatch.setenv("NEWSROOM_LOG_DETERMINISTIC_IDS", "1")
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_oplog2")
    tid, ttok, ctok = begin_pipeline_tick()
    try:
        log_event(log, "op.ctx", flag=1)
    finally:
        reset_tick_id(ttok)
        reset_correlation_id(ctok)
    rec = [r for r in caplog.records if "op.ctx" in r.message][0]
    msg = rec.message
    data = json.loads(msg[msg.index("{") :])
    assert data["correlation_id"] == tid
    assert data["tick_id"] == "tick-000001"
    assert data["event_id"] == "evt-000001"


def test_explicit_fields_override_context(monkeypatch, caplog):
    monkeypatch.setenv("NEWSROOM_LOG_DETERMINISTIC_IDS", "1")
    caplog.set_level(logging.INFO)
    log = logging.getLogger("test_oplog3")
    ctok = set_correlation_id("inner")
    try:
        log_event(log, "op.override", correlation_id="outer", tick_id="manual-tick")
    finally:
        reset_correlation_id(ctok)
    msg = [r for r in caplog.records if "op.override" in r.message][0].message
    data = json.loads(msg[msg.index("{") :])
    assert data["correlation_id"] == "outer"
    assert data["tick_id"] == "manual-tick"
