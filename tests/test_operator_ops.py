"""Operator control, audit search, analytics, transparency."""

from __future__ import annotations

import json

import pytest

from ops.audit.search import search_audit
from ops.control.handlers import dispatch_control_action
from ops.control.journal import append_control_action, query_control_actions
from ops.transparency.export import build_transparency_bundle


def test_control_action_journal(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    append_control_action(rd, action="test.ping", outcome="ok", correlation_id="cid-1")
    rows = query_control_actions(rd, action_prefix="test.")
    assert rows and rows[0]["correlation_id"] == "cid-1"


def test_control_set_mode(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    res = dispatch_control_action(
        ephemeral_newsroom_settings,
        "mode",
        {"mode": "maintenance", "reason": "test"},
        correlation_id="c-test",
    )
    assert res.get("ok") is True
    from app.operational_mode import load_operational_mode

    assert load_operational_mode(rd).value == "maintenance"
    from app.operational_mode import OperationalMode, set_operational_mode

    set_operational_mode(rd, OperationalMode.PRODUCTION, reason="test_reset")


def test_audit_search(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    append_control_action(rd, action="audit.probe", outcome="ok", correlation_id="x")
    out = search_audit(rd, entity="control_action", limit=10)
    assert out["total"] >= 1
    assert out["results"][0]["entity"] == "control_action"


def test_transparency_bundle(ephemeral_newsroom_settings) -> None:
    bundle = build_transparency_bundle(ephemeral_newsroom_settings, hours=1.0)
    assert bundle.get("schema_version") == 1
    assert "governance_decisions" in bundle
