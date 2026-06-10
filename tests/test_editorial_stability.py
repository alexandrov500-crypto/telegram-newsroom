"""Tests for editorial stability & growth layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.stability.elastic_fill import (
    build_context_post_from_buffer,
    pick_elastic_cluster,
    record_cluster_buffer,
)
from app.editorial.stability.growth_decision import evaluate_growth_decision
from app.editorial.stability.mode_controller import (
    PublishingMode,
    primary_governance_suppress_reason,
    resolve_publishing_mode,
    should_bypass_governance,
)
from app.editorial.stability.packaging import apply_editorial_packaging, infer_rubric_tag
from app.editorial.stability.synthesis import build_synthesis_post, mark_synthesis_emitted


def test_primary_governance_suppress_reason_prefers_cooldown() -> None:
    reason = primary_governance_suppress_reason(
        ["trusted_sources", "high_freshness"],
        ["source_cooldown", "source_on_cooldown"],
        gov_reason="",
    )
    assert reason == "source_on_cooldown"


def test_resolve_elastic_fill_when_governance_blocked_and_gap(ephemeral_newsroom_settings, monkeypatch) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    monkeypatch.setenv("EDITORIAL_ANTI_PAUSE_GAP_MINUTES", "30")
    fake_last = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        "app.editorial.stability.anti_pause.last_publish_at_sync",
        lambda: fake_last,
    )
    monkeypatch.setattr(
        "app.editorial.stability.mode_controller.evaluate_anti_pause",
        lambda **kw: evaluate_anti_pause(
            newsroom_tz=kw.get("newsroom_tz", "Europe/Moscow"),
            now=datetime(2026, 5, 30, 9, 0, tzinfo=UTC),
        ),
    )
    ctx = resolve_publishing_mode(
        newsroom_tz="Europe/Moscow",
        cluster_size=1,
        governance_blocked=True,
    )
    assert ctx.mode == PublishingMode.ELASTIC_FILL
    assert ctx.bypass_governance is True


def test_should_not_bypass_on_hard_block(ephemeral_newsroom_settings, monkeypatch) -> None:
    monkeypatch.setenv("EDITORIAL_ANTI_PAUSE_GAP_MINUTES", "30")
    monkeypatch.setattr(
        "app.editorial.stability.anti_pause.last_publish_at_sync",
        lambda: datetime.now(timezone.utc) - timedelta(hours=2),
    )
    ctx = resolve_publishing_mode(governance_blocked=True)
    assert should_bypass_governance(ctx, div_blocked=True, gov_suppress=False, hard_block=True) is False


def test_growth_decision_rejects_low_intel(ephemeral_newsroom_settings) -> None:
    dec = evaluate_growth_decision("Кратко.", quality_score=30.0, publishing_mode="core")
    assert dec.reject is True


def test_growth_decision_anti_pause_overrides_reject(ephemeral_newsroom_settings) -> None:
    dec = evaluate_growth_decision("Кратко.", quality_score=30.0, publishing_mode="elastic_fill")
    assert dec.reject is False


def test_packaging_adds_rubric_tag() -> None:
    body, meta = apply_editorial_packaging(
        "ЦБ сохранил ставку на текущем уровне.",
        editorial_category="macro",
        post_type="news",
    )
    assert "#Экономика" in body or meta.get("rubric_tag") == "#Экономика"


def test_infer_rubric_ai() -> None:
    assert infer_rubric_tag("OpenAI выпустила новую модель GPT", post_type="news") == "#AI"


def test_elastic_buffer_roundtrip(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    record_cluster_buffer(
        rd,
        fingerprint="fp-test",
        combined_text="Нефть дорожает на фоне сокращения добычи.",
        sources=["@rbc_news"],
        topic_hint="oil markets",
        editorial_category="market",
        quality_score=55.0,
    )
    picked = pick_elastic_cluster(rd)
    assert picked is not None
    assert picked.fingerprint == "fp-test"
    post = build_context_post_from_buffer(picked)
    assert "Контекст:" in post
    assert "Почему важно" in post


def test_synthesis_post(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    out = build_synthesis_post(rd)
    assert out is not None
    body, meta = out
    assert "3 вещи" in body
    assert meta.get("post_type") == "digest"
    mark_synthesis_emitted(rd)
    assert build_synthesis_post(rd) is None


def test_evaluate_anti_pause_offhours(ephemeral_newsroom_settings, monkeypatch) -> None:
    monkeypatch.setenv("EDITORIAL_ACTIVE_HOURS_START", "8")
    monkeypatch.setenv("EDITORIAL_ACTIVE_HOURS_END", "22")
    now = datetime(2026, 6, 6, 0, 0, tzinfo=UTC)
    ap = evaluate_anti_pause(newsroom_tz="Europe/Moscow", now=now)
    assert ap.in_active_hours is False
    assert ap.anti_pause_active is False
