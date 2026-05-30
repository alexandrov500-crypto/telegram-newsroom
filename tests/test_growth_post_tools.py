from __future__ import annotations

import pytest

from app.editorial.growth_profile import aggressive_growth_enabled, apply_growth_profile_defaults
from app.editorial.public_post_formatter import format_public_post_plain


def test_aggressive_growth_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSROOM_GROWTH_MODE", raising=False)
    monkeypatch.delenv("NEWSROOM_ENGAGEMENT_HOOK_ENABLED", raising=False)
    monkeypatch.delenv("GROWTH_PHASE", raising=False)
    monkeypatch.setenv("NEWSROOM_GROWTH_MODE", "aggressive")
    apply_growth_profile_defaults()
    assert aggressive_growth_enabled()
    assert __import__("os").getenv("NEWSROOM_ENGAGEMENT_HOOK_ENABLED") == "true"
    assert __import__("os").getenv("GROWTH_PHASE") == "d7"


def test_aggressive_post_includes_ru_growth_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_GROWTH_MODE", "aggressive")
    monkeypatch.setenv("NEWSROOM_ENGAGEMENT_HOOK_ENABLED", "true")
    monkeypatch.setenv("NEWSROOM_OPEN_LOOP_ENABLED", "true")
    monkeypatch.setenv("NEWSROOM_BRAND_FOOTER_ENABLED", "true")
    monkeypatch.setenv("NEWSROOM_SHARE_NUDGE_ENABLED", "true")
    monkeypatch.setenv("NEWSROOM_HASHTAGS_ENABLED", "true")
    body = (
        "ЦБ сохранил ключевую ставку на 12%.\n\n"
        "Регулятор указал на умеренное инфляционное давление и стабильность финансового сектора.\n\n"
        "Почему это важно: решение задаёт траекторию стоимости капитала на ближайшие месяцы."
    )
    out = format_public_post_plain(body, '[{"channel": "@cb_economics"}]', include_cta=True)
    assert "Подписывайтесь" in out
    assert "Почему это важно" in out
    assert "Traders now focus" not in out
    assert "Follow for high-signal" not in out
    assert "#Rates" in out or "Главное для экономики" in out or "Дальше" in out
