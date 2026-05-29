from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.editorial.translate_fallback import translate_cluster_posts, translate_zh_to_ru


@pytest.mark.asyncio
async def test_translate_zh_to_ru_uses_mymemory(monkeypatch):
    monkeypatch.delenv("LIBRETRANSLATE_URL", raising=False)

    async def fake_get(url, params=None):
        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"responseData": {"translatedText": "ЦБ Китая снизил ставку."}}

        return Resp()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        get = fake_get

    monkeypatch.setattr("app.editorial.translate_fallback.httpx.AsyncClient", FakeClient)
    out = await translate_zh_to_ru("中国人民银行宣布降息。")
    assert out
    assert "ЦБ" in out


@pytest.mark.asyncio
async def test_translate_cluster_posts_returns_ru_posts(monkeypatch):
    monkeypatch.setattr(
        "app.editorial.translate_fallback.translate_zh_to_ru",
        AsyncMock(return_value="ВОЗ сообщила о вспышке Эболы в Африке."),
    )
    posts = [
        SimpleNamespace(
            id=1,
            channel_name="@tnews365",
            message_id=99,
            text="世界卫生组织宣布埃博拉疫情。",
            extras="{}",
        )
    ]
    settings = SimpleNamespace(
        source_channel_languages={"@tnews365": "zh"},
        publish_output_language="ru",
    )
    out = await translate_cluster_posts(posts, settings)
    assert out is not None
    assert "ВОЗ" in out[0].text
