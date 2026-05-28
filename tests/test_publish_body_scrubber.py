from __future__ import annotations

from app.editorial.publish_body_scrubber import scrub_publish_plaintext


def test_scrub_json_sources_header() -> None:
    raw = (
        "ЦБ повысил ставку.\n\n"
        "Источники (JSON)\n"
        '[{"channel": "@cb_economics", "message_id": 99}]\n'
        "quality_score: 0.54"
    )
    out = scrub_publish_plaintext(raw)
    assert "Источники (JSON)" not in out
    assert "channel" not in out
    assert "quality_score" not in out
    assert "ЦБ повысил" in out


def test_scrub_pre_and_pipeline() -> None:
    raw = "Hello\n<pre>{\"channel\": \"@x\"}</pre>\nwrapper_exit summarize\ntrace_id: abc"
    out = scrub_publish_plaintext(raw)
    assert "<pre" not in out
    assert "wrapper_exit" not in out
    assert "trace_id" not in out
    assert "Hello" in out


def test_scrub_empty_placeholder_and_cta() -> None:
    raw = "Body line.\n\n(empty)\nПодписывайтесь на канал — главные новости без шума."
    out = scrub_publish_plaintext(raw)
    assert "(empty)" not in out
    assert "Подписывайтесь" not in out
    assert "Body line" in out
