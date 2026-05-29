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
        content="ФРС оставила ставку без изменений. Регулятор указал на устойчивую инфляцию в услугах.",
        extras_json=extras,
    )
    assert ok
    assert reason == "auto_publish_approved"


def test_fastlane_cb_economics_auto_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    monkeypatch.setenv("AUTO_PUBLISH_FASTLANE_SOURCES", "@cb_economics")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=77,
        content=(
            "ФРС оставила ставку без изменений. "
            "Рынок казначейских облигаций отреагировал снижением доходностей."
        ),
        extras_json="{}",
        sources_json='[{"channel":"@cb_economics","message_id":1}]',
    )
    assert ok
    assert reason.startswith("source_fastlane:@cb_economics")


def test_backlog_relief_approves_trusted_high_signal(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    monkeypatch.setenv("AUTO_PUBLISH_BACKLOG_RELIEF_ENABLED", "true")
    monkeypatch.setenv("AUTO_PUBLISH_BACKLOG_RELIEF_MIN_SIGNAL", "0.58")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=88,
        content=(
            "ФРС сохранила ставку на текущем уровне, но указала на длительный период жесткой политики. "
            "Это усиливает давление на доходности и может ограничить рост технологических акций."
        ),
        extras_json="{}",
        sources_json='[{"channel":"@rbc_news","message_id":2}]',
        runtime_dir=str(tmp_path),
        backlog_relief=True,
        stall_level="high",
    )
    assert ok
    assert reason.startswith("backlog_relief_high_tier2:")


def test_backlog_relief_rejects_low_tier_source(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    monkeypatch.setenv("AUTO_PUBLISH_BACKLOG_RELIEF_ENABLED", "true")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=89,
        content=(
            "Рынок обсуждает очередной памп низколиквидного токена. "
            "Это не меняет макрокартину и не дает устойчивого сигнала по потокам капитала."
        ),
        extras_json="{}",
        sources_json='[{"channel":"@random_aggregator_xyz","message_id":7}]',
        runtime_dir=str(tmp_path),
        backlog_relief=True,
    )
    assert not ok
    assert "confidence_below_min" in reason or "quality_" in reason or "duplicate_" in reason


def test_backlog_relief_medium_blocks_tier2(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    monkeypatch.setenv("AUTO_PUBLISH_BACKLOG_RELIEF_ENABLED", "true")
    ok, reason = ap.evaluate_draft_for_auto_publish(
        draft_id=90,
        content=(
            "ФРС сохранила ставку, инфляция замедляется. "
            "Это может снизить давление на длинные доходности и поддержать риск-активы."
        ),
        extras_json="{}",
        sources_json='[{"channel":"@rbc_news","message_id":3}]',
        runtime_dir=str(tmp_path),
        backlog_relief=True,
        stall_level="medium",
    )
    assert not ok
    assert "confidence_below_min" in reason
