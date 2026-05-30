"""Autonomous editorial mode tests."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.editorial.ai_editorial_reviewer import (
    autonomous_editorial_mode_enabled,
    rule_based_editorial_review,
)
from app.ops.autonomous_publish import evaluate_draft_for_auto_publish, settings_force_manual


def _rich_body() -> str:
    return (
        "ФРС сигнализирует о снижении ключевой ставки — рынки переоценивают кривую доходности. "
        "Волатильность растёт, инвесторы смещают позиции в защитные активы. "
        "Почему это важно: изменение ставки перестраивает стоимость капитала."
    )


def test_autonomous_mode_env(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    assert autonomous_editorial_mode_enabled()
    assert not settings_force_manual()


def test_ai_approved_clears_editorial_hold(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    monkeypatch.setenv("AUTO_PUBLISH_ENABLED", "true")
    extras = (
        '{"editorial_hold": true, "ai_editorial_review": {"approved": true, "confidence": 0.8}, '
        '"editorial_confidence": {"confidence_score": 0.75}}'
    )
    ok, reason = evaluate_draft_for_auto_publish(
        draft_id=1,
        content=_rich_body(),
        extras_json=extras,
        sources_json='[{"channel": "@cb_economics"}]',
    )
    assert ok, reason


def test_notify_skipped_in_autonomous_mode(monkeypatch) -> None:
    import asyncio

    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    bot = AsyncMock()
    settings = SimpleNamespace(admin_user_id=1, moderation_chat_id=None)

    async def _run() -> None:
        with patch("bot.admin_handlers.log_event") as log_event:
            from bot.admin_handlers import notify_admin_new_draft

            await notify_admin_new_draft(
                bot,
                settings,  # type: ignore[arg-type]
                draft_id=99,
                content="test",
                sources="[]",
            )
            bot.send_message.assert_not_called()
            assert any("autonomous_skip" in str(c) for c in log_event.call_args_list)

    asyncio.run(_run())


def test_rule_based_rejects_empty() -> None:
    v = rule_based_editorial_review("", settings=SimpleNamespace(runtime_state_dir="var/runtime"))
    assert not v.approved


def test_rules_fallback_when_openai_empty(monkeypatch) -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    monkeypatch.setenv("AI_EDITORIAL_REVIEW_ENABLED", "true")
    monkeypatch.setenv("AI_EDITORIAL_MIN_CONFIDENCE", "0.68")

    async def _run() -> None:
        from app.editorial.ai_editorial_reviewer import ai_editorial_review

        client = AsyncMock()
        choice = MagicMock()
        choice.message.content = ""
        client.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[choice]))
        extras = '{"editorial_confidence": {"confidence_score": 0.56}}'
        v = await ai_editorial_review(
            _rich_body(),
            sources='[{"channel":"@cb_economics"}]',
            extras_json=extras,
            settings=SimpleNamespace(runtime_state_dir="var/runtime", openai_model="gpt-4.1"),
            openai_client=client,
        )
        assert v.approved, v.reason
        assert v.reason == "rules_fallback_openai_error"

    asyncio.run(_run())
