"""
Public post contract — 10 mandatory guarantees for every channel publication.

SSOT: format_public_post_html → render_subscriber_wire_html (+ pre-send guards).
Каждый тест закрывает один пункт обязательных проверок аудита:
debug / JSON / реклама / длина / источник / единый формат / свежесть /
слабый источник / дубли / целостность Telegram HTML.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.editorial.public_post_formatter import format_public_post_html

_SOURCES = '[{"channel": "@cb_economics", "message_id": 100}]'

_CLEAN_STORY = (
    "ЦБ сохранил ключевую ставку на уровне 16% годовых.\n\n"
    "Совет директоров отметил замедление инфляции до 5,2% в годовом выражении. "
    "Регулятор сохранил умеренно жёсткий сигнал по денежно-кредитной политике. "
    "Рынки ожидают начала смягчения на следующем заседании в июле. "
    "Это повлияет на доходности ОФЗ и ставки по депозитам в ближайшие месяцы."
)


@pytest.fixture(autouse=True)
def _wire_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "subscriber_wire")
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "true")
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "true")
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("WIRE_POST_THESIS_BULLETS", "true")
    monkeypatch.setenv("WIRE_POST_INTEGRATED_CLOSURE", "false")
    monkeypatch.setenv("WIRE_POST_WHY_BLOCK", "true")
    monkeypatch.setenv("PUBLIC_WHY_IT_MATTERS", "true")


def _render(content: str, sources: str = _SOURCES) -> str:
    return format_public_post_html(content, sources, max_total_chars=4096)


# 1. Пост не должен содержать debug-информацию.
def test_post_contains_no_debug_info() -> None:
    polluted = (
        _CLEAN_STORY
        + "\n\ntrace_id: abc-123\nquality: 0.87\nDraft #42 status: approved\nPIPELINE_FATAL"
    )
    html = _render(polluted)
    low = html.lower()
    for marker in ("trace_id", "draft #", "pipeline_fatal", "quality:", "wrapper_exit"):
        assert marker not in low, f"debug marker leaked: {marker}"


def test_sanitizer_blocks_planted_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.editorial.public_content_sanitizer import evaluate_public_content_sanitizer

    res = evaluate_public_content_sanitizer(
        "<b>Заголовок</b>\n\ntrace_id: xyz", strict=True
    )
    assert res.blocked
    assert "pipeline_terms" in res.violations


# 2. Пост не должен содержать JSON.
def test_post_contains_no_json() -> None:
    polluted = _CLEAN_STORY + '\n\n[{"channel": "@leak", "message_id": 5}]'
    html = _render(polluted)
    assert '{"channel"' not in html
    assert "message_id" not in html


def test_quality_gate_blocks_json_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.editorial.publish_quality_gate import evaluate_publish_quality_gate

    monkeypatch.setenv("PUBLISH_QUALITY_GATE_STRICT", "true")
    res = evaluate_publish_quality_gate('<b>X</b>\n\n{"channel": "@leak"}')
    assert not res.ok
    assert "json_channel" in res.block_reasons


# 3. Пост не должен содержать рекламных фраз.
def test_ad_phrases_detected_and_blocked() -> None:
    from app.editorial.content_quality import has_hidden_advertising
    from app.ops.floor_eligibility import evaluate_floor_eligibility

    ad = (
        "Ставки по вкладам выросли. Подписывайтесь на наш канал и получите "
        "промокод SALE20 — переходите по ссылке https://x.io/?utm_source=tg."
    )
    assert has_hidden_advertising(ad)
    verdict = evaluate_floor_eligibility(ad, sources_json=_SOURCES)
    assert not verdict.eligible
    assert verdict.reason == "hidden_advertising"


# 4. Пост не должен быть длиннее допустимого лимита.
def test_post_not_longer_than_telegram_limit() -> None:
    long_story = " ".join(
        f"Показатель номер {i} вырос на {i % 9 + 1}% за отчётный период, что "
        "отражает устойчивую динамику в секторе."
        for i in range(120)
    )
    html = _render(long_story)
    assert 0 < len(html) <= 4096


# 5. Пост должен иметь источник в конце.
def test_source_footer_at_end() -> None:
    html = _render(_CLEAN_STORY)
    lines = [ln for ln in html.splitlines() if ln.strip()]
    assert lines, "empty render"
    assert "Источник: @cb_economics" in lines[-1]


# 6. Пост должен иметь единый формат: headline → body → (why) → source.
def test_unified_format_structure() -> None:
    html = _render(_CLEAN_STORY)
    head_idx = html.find("<b>")
    src_idx = html.find("Источник:")
    assert head_idx == 0 or html[:head_idx].strip() in {"", "⚡"}
    assert src_idx > head_idx > -1
    body_plain = re.sub(r"<[^>]+>", "", html[:src_idx])
    assert len(body_plain.strip()) >= 120, "body missing or headline-only stub"
    why_idx = html.find("Почему это важно:")
    if why_idx != -1:
        assert head_idx < why_idx < src_idx


# 7. Пост не должен публиковаться, если новость устарела.
def test_stale_news_not_published(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ops.autonomous_publish import _is_stale_pending

    monkeypatch.setenv("AUTO_PUBLISH_STALE_PENDING_HOURS", "72")
    stale = SimpleNamespace(created_at=datetime.now(UTC) - timedelta(hours=100))
    fresh = SimpleNamespace(created_at=datetime.now(UTC) - timedelta(hours=1))
    assert _is_stale_pending(stale)
    assert not _is_stale_pending(fresh)


# 8. Пост не должен публиковаться при низком качестве источника без подтверждения.
def test_low_quality_single_source_gate_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.editorial.wire_recovery import wire_bypass_rumor_single_source

    monkeypatch.setenv("WIRE_RECOVERY_ENABLED", "false")
    assert wire_bypass_rumor_single_source(sources=["@unknown_channel"]) is False


# 9. Пост не должен публиковаться повторно при похожей новости.
def test_near_duplicate_story_blocked(tmp_path) -> None:
    from app.editorial.cadence_intelligence import (
        evaluate_cadence_intelligence,
        record_cadence_intelligence,
    )

    settings = SimpleNamespace(publish_burst_window_sec=120.0, publish_burst_max_messages=4)
    runtime = str(tmp_path)
    story = (
        "Индекс Мосбиржи снизился на 1,8% на фоне падения нефтяных котировок "
        "и укрепления рубля к доллару."
    )
    record_cadence_intelligence(runtime, content=story, topic_key="moex_drop")
    blocked, reasons = evaluate_cadence_intelligence(
        settings, runtime, content=story, topic_key=""
    )
    assert blocked
    assert "cadence_intel_near_identical_story" in reasons


# 10. Telegram HTML не должен ломаться.
def _assert_balanced_html(html: str) -> None:
    for tag in ("b", "i", "code", "blockquote"):
        opened = len(re.findall(rf"<{tag}>", html))
        closed = len(re.findall(rf"</{tag}>", html))
        assert opened == closed, f"unbalanced <{tag}>: {opened} vs {closed}"
    leftover = re.sub(r"</?(?:b|i|code|blockquote|a)\b[^>]*>", "", html)
    assert "<" not in leftover, f"raw angle bracket in rendered html: {leftover[:120]}"


def test_telegram_html_integrity() -> None:
    html = _render(_CLEAN_STORY + " Компания <X&Co> заявила о росте на 5%.")
    _assert_balanced_html(html)
    assert "<X&Co>" not in html  # raw angle brackets must be escaped


def test_safe_truncation_keeps_html_valid() -> None:
    from app.editorial.public_post_formatter import _truncate_html_safely

    html = _render(_CLEAN_STORY)
    truncated = _truncate_html_safely(html, max_chars=max(60, len(html) // 2))
    _assert_balanced_html(truncated)


# Fast lane обязан использовать SSOT: без debug-хвостов и внутренних футеров.
def test_fast_lane_uses_ssot_renderer() -> None:
    from app.worker.fast_publish import build_breaking_html

    html = build_breaking_html(
        "СРОЧНО: ЦБ повысил ставку на 200 б.п. до 18% годовых.\n\n"
        "Решение принято на внеочередном заседании из-за ускорения инфляции. "
        "Регулятор допускает дальнейшее ужесточение политики осенью.",
        [{"channel": "@cb_economics", "message_id": 7}],
        article_id="brk:deadbeef123456",
    )
    assert "Fast lane" not in html
    assert "deadbeef" not in html
    assert "message_id" not in html
    assert "Sources" not in html
    assert "Источник: @cb_economics" in html
    _assert_balanced_html(html)
