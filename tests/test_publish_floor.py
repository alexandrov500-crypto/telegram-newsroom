"""Guaranteed publishing floor: algorithm/editorial changes must never silence the channel."""

from __future__ import annotations

import pytest

from app.editorial.final_publish_gate import evaluate_final_publish_gate


_SOURCES = '[{"channel": "@cb_economics"}]'


def test_safety_only_allows_low_signal_story_that_editorial_gate_rejects() -> None:
    """A finished but 'low-signal' bureaucratic note is editorially rejected,
    yet must still be publishable under the safety-only floor."""
    text = (
        "ФТС утвердила форму предписания о выезде транспорта с товарами за пределы РФ. "
        "Документ определяет шаблон и порядок заполнения формы."
    )
    editorial = evaluate_final_publish_gate(content=text, sources=_SOURCES, operator_approved=False)
    floor = evaluate_final_publish_gate(content=text, sources=_SOURCES, safety_only=True)
    # Editorial path rejects as low-signal; floor path allows (safety only).
    assert editorial.reason in {"premium_policy_low_signal", "incomplete_public_template"}
    assert floor.allowed


def test_safety_only_still_blocks_hidden_advertising() -> None:
    text = (
        "Партнерский материал: используйте промокод NEWS10 и переходите по ссылке "
        "для скидки на тариф."
    )
    floor = evaluate_final_publish_gate(content=text, sources=_SOURCES, safety_only=True)
    assert not floor.allowed
    assert floor.reason in {"hidden_advertising", "incomplete_teaser_no_body"}


def test_safety_only_still_blocks_teaser_without_body() -> None:
    text = "Смотрите на картинке."
    floor = evaluate_final_publish_gate(content=text, sources=_SOURCES, safety_only=True)
    assert not floor.allowed
    assert floor.reason == "incomplete_teaser_no_body"


def test_floor_disabled_returns_no_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ops import autonomous_publish as ap

    monkeypatch.setenv("PUBLISH_FLOOR_ENABLED", "false")
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")

    import asyncio

    async def _run() -> None:
        out = await ap.select_floor_publish_candidate(settings=None, session=None)
        assert out is None

    asyncio.run(_run())


def test_safety_only_allows_geopolitics_note_editorial_rejects() -> None:
    """Pashinyan-style geopolitical note: editorially 'low-signal' (no explicit
    market implication) but the operator/floor must be able to ship it."""
    text = (
        "Пашинян анонсировал строительство транзитного газопровода через территорию Армении. "
        "Премьер-министр Армении заявил, что по территории страны пройдёт газопровод, "
        "а за транзит страна будет получать газ."
    )
    editorial = evaluate_final_publish_gate(content=text, sources=_SOURCES, operator_approved=False)
    floor = evaluate_final_publish_gate(content=text, sources=_SOURCES, safety_only=True)
    assert not editorial.allowed
    assert floor.allowed


def test_floor_silence_threshold_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ops import autonomous_publish as ap

    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "120")
    assert ap._floor_max_silence_min() == 120.0
    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "5")
    # Clamped to a sane minimum.
    assert ap._floor_max_silence_min() == 30.0


def test_floor_falls_back_to_quality_failed_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no clean pending draft exists, the floor must reach into recent
    quality-failed drafts (e.g. fallback summaries judged 'low-signal') so the
    channel never goes dark, picking the freshest viable one."""
    import asyncio
    from types import SimpleNamespace

    from app.ops import autonomous_publish as ap

    monkeypatch.setenv("PUBLISH_FLOOR_ENABLED", "true")
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "90")

    fresh = SimpleNamespace(
        id=72,
        content=(
            "Пашинян анонсировал строительство транзитного газопровода через территорию Армении. "
            "Премьер-министр Армении заявил, что за транзит страна будет получать газ."
        ),
    )

    async def _stall(*_a, **_k):
        return {"minutes_since_last_published": 120.0, "pending_backlog": 0, "incoming_raw_flow_30m": 0}

    async def _no_pending(*_a, **_k):
        return []

    async def _quality_failed(*_a, **_k):
        return [fresh]

    monkeypatch.setattr(ap, "auto_publish_enabled", lambda: True)
    monkeypatch.setattr(ap, "detect_publish_stall_risk", _stall)
    monkeypatch.setattr("db.repository.list_pending_drafts", _no_pending)
    monkeypatch.setattr("db.repository.list_recent_quality_failed_drafts", _quality_failed)

    async def _run() -> None:
        out = await ap.select_floor_publish_candidate(settings=object(), session=object())
        assert out is not None
        assert out["draft_id"] == 72

    asyncio.run(_run())


def test_rule_fallback_keeps_drafts_flowing_when_openai_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OpenAI is unavailable, the rule-based summarizer must keep producing
    drafts so the channel never runs dry on fresh content."""
    import app.reliability.summarize_fallback as sf

    # Isolate from real desk-starvation / burn-in runtime state.
    monkeypatch.setattr(sf, "_starvation_fallback_active", lambda: False)
    monkeypatch.setenv("SUMMARIZE_RULE_FALLBACK_WHEN_AI_DOWN", "true")
    assert sf._rule_fallback_when_ai_down() is True
    assert sf.fallback_allowed(bypass=False, minimal_mode=False) is True
    monkeypatch.setenv("SUMMARIZE_RULE_FALLBACK_WHEN_AI_DOWN", "false")
    assert sf._rule_fallback_when_ai_down() is False
