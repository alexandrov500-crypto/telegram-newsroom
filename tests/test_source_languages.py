"""Tests for multilingual source → RU output resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.editorial.source_languages import (
    cluster_source_language,
    detect_text_language,
    parse_source_channel_languages,
    requires_translation,
    text_violates_output_language,
    translation_context_for_cluster,
)


def test_parse_source_channel_languages():
    raw = "@tnews365:zh,@cb_economics:ru,@DeCenter:ru"
    assert parse_source_channel_languages(raw) == {
        "@tnews365": "zh",
        "@cb_economics": "ru",
        "@decenter": "ru",
    }


def test_detect_text_language():
    assert detect_text_language("ЦБ повысил ключевую ставку") == "ru"
    assert detect_text_language("中国人民银行发布重要通知，市场关注利率走向。") == "zh"
    assert detect_text_language("Fed holds rates steady amid inflation data") == "en"


def test_cluster_source_language_uses_channel_config():
    posts = [
        SimpleNamespace(
            channel_name="@tnews365",
            text="中国人民银行发布重要通知",
            extras="{}",
        )
    ]
    settings = SimpleNamespace(
        source_channel_languages={"@tnews365": "zh"},
        publish_output_language="ru",
    )
    assert cluster_source_language(posts, settings) == "zh"
    ctx = translation_context_for_cluster(posts, settings)
    assert ctx["translation_required"] is True
    assert requires_translation(ctx["source_language"], ctx["output_language"])


def test_cjk_leak_blocks_ru_output():
    assert text_violates_output_language("Курс юаня 中国人民银行", output_language="ru")
    assert not text_violates_output_language("Курс юаня ослаб", output_language="ru")


def test_fallback_not_allowed_for_zh_cluster(monkeypatch):
    from app.reliability.summarize_fallback import fallback_allowed

    posts = [
        SimpleNamespace(
            channel_name="@tnews365",
            text="中国人民银行",
            extras='{"source_language":"zh"}',
        )
    ]
    settings = SimpleNamespace(
        source_channel_languages={"@tnews365": "zh"},
        publish_output_language="ru",
    )
    assert fallback_allowed(bypass=False, minimal_mode=False, cluster=posts, settings=settings) is False


def test_final_publish_gate_blocks_cjk_leak():
    from app.editorial.final_publish_gate import evaluate_final_publish_gate

    verdict = evaluate_final_publish_gate(
        content="Новость дня: 中国人民银行调整政策",
        sources="@tnews365",
        operator_approved=False,
    )
    assert not verdict.allowed
    assert verdict.reason == "output_language_cjk_leak"
