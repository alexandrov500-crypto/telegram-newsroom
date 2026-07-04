"""Tests for top news-channel beat preset."""

from __future__ import annotations

import pytest

from app.editorial.news_channel_beat import (
    apply_news_channel_beat_defaults,
    news_beat_topic_cooldown_sec,
    news_channel_beat_enabled,
)


def test_beat_enabled_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    assert news_channel_beat_enabled() is True


def test_beat_disabled_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "off")
    monkeypatch.setenv("NEWSROOM_GROWTH_MODE", "aggressive")
    assert news_channel_beat_enabled() is False


def test_topic_cooldown_shorter_in_beat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "true")
    assert news_beat_topic_cooldown_sec(default=1800.0) == 600.0


def test_apply_defaults_sets_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "true")
    for key in ("PIPELINE_INTERVAL_MINUTES", "AUTONOMOUS_EDITORIAL_MODE"):
        monkeypatch.delenv(key, raising=False)
    before = dict(os.environ)
    try:
        apply_news_channel_beat_defaults()
        assert os.environ["PIPELINE_INTERVAL_MINUTES"] == "3"
        assert os.environ["AUTONOMOUS_EDITORIAL_MODE"] == "true"
        assert os.environ["PUBLIC_WHY_IT_MATTERS"] == "true"
        assert os.environ["WIRE_POST_INTEGRATED_CLOSURE"] == "false"
    finally:
        # apply_news_channel_beat_defaults writes os.environ directly —
        # roll back so ~100 defaults don't leak into unrelated tests.
        for key in list(os.environ):
            if key not in before:
                os.environ.pop(key, None)
            elif os.environ[key] != before[key]:
                os.environ[key] = before[key]
