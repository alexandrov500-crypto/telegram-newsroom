"""Tests for W1 floor safety — premium gate preserved, no quality-failed fallback."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.editorial.final_publish_gate import evaluate_final_publish_gate
from app.ops import autonomous_publish as ap
from app.ops.floor_eligibility import evaluate_floor_eligibility

_SOURCES = '[{"channel": "@cb_economics"}]'


def test_floor_does_not_use_safety_only_bypass_for_premium() -> None:
    """Low-signal bureaucratic note must fail floor eligibility AND full gate."""
    text = (
        "ФТС утвердила форму предписания о выезде транспорта с товарами за пределы РФ. "
        "Документ определяет шаблон и порядок заполнения формы."
    )
    floor_elig = evaluate_floor_eligibility(text, sources_json=_SOURCES)
    editorial = evaluate_final_publish_gate(content=text, sources=_SOURCES, operator_approved=False)
    assert not floor_elig.eligible
    assert not editorial.allowed


def test_floor_full_gate_still_blocks_advertising() -> None:
    text = (
        "Партнерский материал: используйте промокод NEWS10 и переходите по ссылке "
        "для скидки на тариф."
    )
    floor = evaluate_final_publish_gate(content=text, sources=_SOURCES, safety_only=False)
    assert not floor.allowed


def test_floor_disabled_returns_no_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLISH_FLOOR_ENABLED", "false")
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")

    async def _run() -> None:
        out = await ap.select_floor_publish_candidate(settings=None, session=None)
        assert out is None

    asyncio.run(_run())


def test_floor_silence_threshold_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "120")
    assert ap._floor_max_silence_min() == 120.0
    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "5")
    assert ap._floor_max_silence_min() == 30.0


def test_floor_picks_eligible_pending_not_quality_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLISH_FLOOR_ENABLED", "true")
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("PUBLISH_FLOOR_MAX_SILENCE_MIN", "90")

    good = SimpleNamespace(
        id=72,
        content=(
            "Пашинян анонсировал строительство транзитного газопровода через территорию Армении. "
            "Премьер-министр Армении заявил, что за транзит страна будет получать газ. "
            "Проект может усилить геополитическое давление на регион и повлиять на цены на энергоносители."
        ),
        sources=_SOURCES,
    )

    async def _stall(*_a, **_k):
        return {"minutes_since_last_published": 120.0, "pending_backlog": 0, "incoming_raw_flow_30m": 0}

    async def _pending(*_a, **_k):
        return [good]

    monkeypatch.setattr(ap, "auto_publish_enabled", lambda: True)
    monkeypatch.setattr(ap, "detect_publish_stall_risk", _stall)
    monkeypatch.setattr("db.repository.list_pending_drafts", _pending)

    async def _run() -> None:
        out = await ap.select_floor_publish_candidate(settings=object(), session=object())
        assert out is not None
        assert out["draft_id"] == 72
        assert out.get("floor_score", 0) >= 0.72

    asyncio.run(_run())
