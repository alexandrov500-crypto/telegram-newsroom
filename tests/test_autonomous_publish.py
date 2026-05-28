"""Autonomous publish policy tests."""

from __future__ import annotations

import json

import pytest

from app.ops import autonomous_publish as ap


def test_auto_publish_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_PUBLISH_ENABLED", raising=False)
    monkeypatch.setenv("AUTO_APPROVE_DRAFTS", "false")
    monkeypatch.setenv("FINAL_STAGING_MODE", "true")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=1,
        content="x" * 100,
        extras_json="{}",
    )
    assert not ok
    assert "disabled" in reason


def test_rejects_short_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=1,
        content="short",
        extras_json="{}",
    )
    assert not ok
    assert "too_short" in reason


def test_approves_high_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    extras = json.dumps({"editorial_confidence": {"confidence_score": 0.85}})
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=1,
        content="A" * 120,
        extras_json=extras,
    )
    assert ok
    assert reason == "auto_publish_approved"
