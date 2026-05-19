from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.processing import summarizer as sm


def _llm_response(payload: dict) -> tuple[str, MagicMock]:
    body = json.dumps(payload)
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=body))]
    response.usage = MagicMock(total_tokens=42)
    return body, response


def test_successful_openai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    sm.bootstrap_env()

    payload = {
        "title": "SEC approves new crypto ETF framework",
        "summary": (
            "Regulators introduced updated ETF guidance focused on custody "
            "transparency and institutional compliance requirements."
        ),
        "tags": ["crypto", "etf", "regulation"],
        "confidence": 0.91,
    }
    _, response = _llm_response(payload)

    async def run() -> dict:
        with patch.object(
            sm, "_call_openai_chat", AsyncMock(return_value=(json.dumps(payload), response))
        ):
            return await sm.summarize_news(
                "SEC approves new crypto ETF framework",
                "https://example.com/sec-etf",
                "reuters",
            )

    result = asyncio.run(run())
    assert result["title"] == payload["title"]
    assert "ETF guidance" in result["summary"]
    assert result["tags"] == ["crypto", "etf", "regulation"]
    assert result["confidence"] == pytest.approx(0.91)


def test_invalid_json_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    sm.bootstrap_env()

    bad_response = MagicMock()
    bad_response.choices = [MagicMock(message=MagicMock(content="not-json"))]
    bad_response.usage = None

    async def run() -> dict:
        with patch.object(
            sm,
            "_call_openai_chat",
            AsyncMock(return_value=("not-json", bad_response)),
        ):
            return await sm.summarize_news("AI chip demand rises", "https://x.com/a", "feed")

    result = asyncio.run(run())
    assert result["confidence"] == 0.0
    assert "Short summary:" in result["summary"]
    assert result["title"] == "AI chip demand rises"


def test_timeout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    sm.bootstrap_env()

    async def run() -> dict:
        with patch.object(
            sm,
            "_call_openai_chat",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            return await sm.summarize_news("Markets steady", "https://x.com/b", "feed")

    result = asyncio.run(run())
    assert result["confidence"] == 0.0
    assert result["summary"].startswith("Short summary:")


def test_missing_api_key_fallback() -> None:
    async def run() -> dict:
        with (
            patch.object(sm, "get_openai_api_key", return_value=None),
            patch.object(sm, "_llm_summarize", AsyncMock()) as llm_mock,
        ):
            result = await sm.summarize_news("Local headline", "https://x.com/c", "feed")
        llm_mock.assert_not_called()
        return result

    result = asyncio.run(run())
    assert result["confidence"] == 0.0
    assert "Local headline" in result["summary"]


def test_summarize_never_raises_on_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    sm.bootstrap_env()

    async def run() -> dict:
        with patch.object(
            sm,
            "_call_openai_chat",
            AsyncMock(side_effect=RuntimeError("api down")),
        ):
            return await sm.summarize_news("Wire item", "https://x.com/d", "feed")

    result = asyncio.run(run())
    assert isinstance(result, dict)
    assert "title" in result
    assert "summary" in result
    assert "tags" in result


def test_parse_llm_payload_rejects_empty_summary() -> None:
    with pytest.raises(ValueError, match="empty"):
        sm._parse_llm_payload(
            json.dumps({"title": "T", "summary": "", "tags": ["a", "b"], "confidence": 0.5}),
            fallback_title="T",
        )
