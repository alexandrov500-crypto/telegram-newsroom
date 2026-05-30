from __future__ import annotations

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.reference_model import (
    filter_source_channels,
    is_reference_source,
    reference_model_desk_reject,
    reference_model_enabled,
)
from app.editorial.scoring_engine import score_story
from app.ops.autonomous_publish import evaluate_draft_for_auto_publish


def test_reference_model_enabled_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSROOM_REFERENCE_MODEL", raising=False)
    assert not reference_model_enabled()
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    assert reference_model_enabled()


def test_cb_economics_is_reference_source() -> None:
    assert is_reference_source("@cb_economics")
    assert is_reference_source("rbc_news")
    assert not is_reference_source("@DeCenter")


def test_filter_drops_non_reference_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    filtered = filter_source_channels(
        ["@cb_economics", "@DeCenter", "@tnews365", "@vedomosti"]
    )
    assert "@cb_economics" in filtered
    assert "@vedomosti" in filtered
    assert "@DeCenter" not in filtered
    assert "@tnews365" not in filtered


def test_desk_rejects_decenter_under_reference_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    text = (
        "Strategy внесли 411.5 BTC на Coinbase Prime — на Polymarket вероятность продажи "
        "до 31 декабря 2026 года достигла 84%."
    )
    escore = score_story(text=text, sources=["@DeCenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@DeCenter"])
    assert not desk.publish
    assert desk.reason.startswith("reference_model_")


def test_desk_allows_cb_macro_story(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    text = (
        "Росстат: дефляция в России замедлилась в январе, "
        "индекс потребительских цен показал снижение давления на рынке."
    )
    escore = score_story(text=text, sources=["@cb_economics"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics"])
    assert desk.publish
    assert desk.editorial_category in {"macro", "market", "breaking"}


def test_reference_model_rejects_crypto_teaser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    reason = reference_model_desk_reject(
        "Bitcoin to the moon 100x — полный разбор в premium-канале.",
        ["@cb_economics"],
        "market",
    )
    assert reason == "reference_model_crypto_teaser"


def test_fastlane_auto_publish_for_rbc_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("FINAL_STAGING_MODE", "false")
    monkeypatch.setenv("LIVE_SUPERVISED_APPROVAL", "false")
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")
    text = (
        "ЦБ сохранил ключевую ставку на прежнем уровне. "
        "Регулятор указал на умеренное инфляционное давление и стабильность финансового сектора."
    )
    ok, reason = evaluate_draft_for_auto_publish(
        draft_id=1,
        content=text,
        extras_json="{}",
        sources_json='[{"channel":"@rbc_news","message_id":1}]',
    )
    assert ok, reason
    assert "source_fastlane" in reason


def test_reference_model_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "off")
    assert not reference_model_enabled()
    filtered = filter_source_channels(["@cb_economics", "@DeCenter"])
    assert filtered == ("@cb_economics", "@DeCenter")
